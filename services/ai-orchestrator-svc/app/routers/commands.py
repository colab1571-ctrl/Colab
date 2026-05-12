"""
POST /ai/chat/{room_id}/command — dispatch 5 in-chat AI commands.

Premium-only gate via billing-svc entitlement check.
Rate limit: 10 commands per user per minute (Redis sliding window).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import get_ai_settings
from app.db import get_db
from app.models import AIInteraction, MockupAsset
from app.schemas.commands import (
    CommandAsyncResponse,
    CommandRequest,
    CommandSyncResponse,
    InsufficientCreditsError,
    UpsellPayload,
)
from app.services.billing_client import (
    EntitlementError,
    InsufficientCreditsError as BillingInsufficientCreditsError,
    check_entitlement,
    commit_reservation,
    release_reservation,
    reserve_credits,
)
from app.services.moderation_client import scan_text
from app.services.openai_client import chat_complete, moderate_text

router = APIRouter(prefix="/ai", tags=["ai-commands"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_redis(request: Request) -> aioredis.Redis:
    return request.app.state.redis


def _get_http(request: Request) -> httpx.AsyncClient:
    return request.app.state.http


def _get_user_id(request: Request) -> uuid.UUID:
    user_id_str = request.headers.get("X-User-Id", "")
    try:
        return uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(status_code=401, detail="Missing or invalid X-User-Id")


async def _rate_limit(user_id: uuid.UUID, redis: aioredis.Redis, limit: int) -> None:
    """Sliding window rate limit: max `limit` calls per 60s per user."""
    key = f"ai:rate:{user_id}"
    pipe = redis.pipeline()
    pipe.incr(key)
    pipe.expire(key, 60)
    count, _ = await pipe.execute()
    if count > limit:
        raise HTTPException(status_code=429, detail="Rate limit exceeded: max 10 AI commands per minute")


def _credit_cost(command: str, tier: str) -> int:
    settings = get_ai_settings()
    costs = {
        "mockup-image": settings.credit_mockup_image_pro if tier == "pro" else settings.credit_mockup_image_basic,
        "mockup-audio": settings.credit_mockup_audio_pro if tier == "pro" else settings.credit_mockup_audio_basic,
        "summarize-chat": settings.credit_summarize_chat,
        "brainstorm": settings.credit_brainstorm,
        "palette": settings.credit_palette,
    }
    return costs.get(command, 5)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def _handle_summarize(
    room_id: uuid.UUID,
    n: int,
    db: AsyncSession,
    http: httpx.AsyncClient,
) -> tuple[str, int, int]:
    """Fetch last N messages from chat-svc and summarize via OpenAI."""
    settings = get_ai_settings()
    n = max(5, min(200, n))
    try:
        resp = await http.get(
            f"{settings.chat_svc_url}/internal/rooms/{room_id}/messages",
            params={"limit": n, "status": "delivered"},
            timeout=10.0,
        )
        resp.raise_for_status()
        msgs = resp.json().get("messages", [])
    except Exception:
        msgs = []

    transcript_lines = []
    for m in reversed(msgs):
        msg_type = m.get("message_type", "text")
        if msg_type == "text":
            transcript_lines.append(f"[{m.get('sender_display_name', 'User')}]: {m.get('body', '')}")
        else:
            transcript_lines.append(f"[{m.get('sender_display_name', 'User')}]: [{msg_type}]")
    transcript = "\n".join(transcript_lines) or "(no messages)"

    messages = [
        {
            "role": "system",
            "content": (
                f"You are an assistant summarizing a creative collaboration chat. "
                f"Summarize the following {n} messages into 3–5 bullet points covering: "
                "decisions made, action items, creative ideas raised, and any blockers. "
                "Be neutral. Do not editorialize. Output only the bullet list."
            ),
        },
        {"role": "user", "content": f"---\n{transcript}\n---"},
    ]
    return await chat_complete(messages, max_tokens=800)


async def _handle_brainstorm(
    topic: str,
    user_id: uuid.UUID,
    http: httpx.AsyncClient,
) -> tuple[str, int, int]:
    """Generate brainstorm ideas via OpenAI."""
    settings = get_ai_settings()
    # Fetch vocation context (best-effort)
    vocations_a = "various creative fields"
    vocations_b = "various creative fields"
    try:
        resp = await http.get(
            f"{settings.profile_svc_url}/internal/profiles/{user_id}/vocations",
            timeout=3.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            vocations_a = ", ".join(data.get("vocations", [])) or vocations_a
    except Exception:
        pass

    messages = [
        {
            "role": "system",
            "content": (
                f"You are a creative collaborator. The two artists on this project specialize in: "
                f"{vocations_a} and {vocations_b}. "
                "Brainstorm 5–7 distinct creative ideas or angles on the following topic. "
                "Be specific and actionable. Keep each idea to 1–2 sentences."
            ),
        },
        {"role": "user", "content": f"Topic: {topic}"},
    ]
    return await chat_complete(messages, max_tokens=1000)


async def _handle_palette(description: str) -> tuple[str, int, int]:
    """Generate a color palette via OpenAI."""
    settings = get_ai_settings()
    messages = [
        {
            "role": "system",
            "content": (
                "You are a visual designer. Generate a color palette of exactly 5 colors that fits "
                "the following mood/concept. Output ONLY a JSON array of objects: "
                '[{"name": "...", "hex": "#RRGGBB", "usage_note": "..."}]. No prose outside the JSON.'
            ),
        },
        {"role": "user", "content": f"Concept: {description}"},
    ]
    return await chat_complete(
        messages,
        model=settings.openai_model_palette,
        max_tokens=300,
    )


# ---------------------------------------------------------------------------
# Main route
# ---------------------------------------------------------------------------

@router.post("/chat/{room_id}/command")
async def run_command(
    room_id: uuid.UUID,
    body: CommandRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Any:
    settings = get_ai_settings()
    redis = _get_redis(request)
    http = _get_http(request)
    user_id = _get_user_id(request)

    # Rate limit
    await _rate_limit(user_id, redis, settings.command_rate_per_minute)

    # Entitlement check
    try:
        entitlement = await check_entitlement(user_id, http)
        tier = entitlement.get("tier", "premium")
    except EntitlementError:
        interaction = AIInteraction(
            user_id=user_id,
            room_id=room_id,
            command=body.command.replace("-", "_"),
            args_json=body.args.model_dump(),
            cost_credits=0,
            status="rejected_insufficient_credits",
        )
        db.add(interaction)
        await db.commit()
        raise HTTPException(
            status_code=402,
            detail=InsufficientCreditsError().model_dump(),
        )

    cost = _credit_cost(body.command, tier)

    # Create AIInteraction record
    interaction = AIInteraction(
        user_id=user_id,
        room_id=room_id,
        command=body.command.replace("-", "_"),
        args_json=body.args.model_dump(),
        cost_credits=cost,
        status="queued",
    )
    db.add(interaction)
    await db.flush()  # get interaction.id

    # Reserve credits
    try:
        reservation_id = await reserve_credits(user_id, cost, interaction.id, http)
        interaction.billing_reservation_id = reservation_id
        await db.commit()
    except BillingInsufficientCreditsError:
        interaction.status = "rejected_insufficient_credits"
        await db.commit()
        raise HTTPException(
            status_code=402,
            detail=InsufficientCreditsError().model_dump(),
        )

    # Pre-generation prompt moderation
    prompt_text = body.args.prompt or ""
    if prompt_text:
        mod_score = await moderate_text(prompt_text)
        if mod_score >= settings.moderation_pre_gen_threshold:
            interaction.status = "moderation_blocked"
            interaction.failure_reason = f"Pre-generation moderation score: {mod_score:.3f}"
            await db.commit()
            await release_reservation(reservation_id, "moderation_pre_gen", http)
            raise HTTPException(status_code=422, detail="Prompt contains potentially unsafe content")

    # ---------------------------------------------------------------------------
    # Synchronous commands
    # ---------------------------------------------------------------------------

    if body.command == "summarize-chat":
        n = body.args.n if body.args.n else 50
        try:
            content, input_tokens, output_tokens = await _handle_summarize(room_id, n, db, http)
        except Exception as exc:
            logger.error("summarize-chat failed: %s", exc)
            interaction.status = "failed"
            interaction.failure_reason = str(exc)
            await db.commit()
            await release_reservation(reservation_id, "openai_error", http)
            raise HTTPException(status_code=500, detail="Summary generation failed. Credits refunded.")

        # Moderation on output
        mod_score = await scan_text(content, http)
        if mod_score >= settings.moderation_block_threshold:
            interaction.status = "moderation_blocked"
            await db.commit()
            await release_reservation(reservation_id, "moderation_output", http)
            raise HTTPException(status_code=422, detail="AI output blocked by moderation. Credits refunded.")

        interaction.status = "completed"
        interaction.input_tokens = input_tokens
        interaction.output_tokens = output_tokens
        interaction.completed_at = datetime.now(timezone.utc)
        await db.commit()
        await commit_reservation(reservation_id, http)

        from app.schemas.commands import AITextResult
        return CommandSyncResponse(
            ai_interaction_id=interaction.id,
            command="summarize-chat",
            result=AITextResult(
                command="summarize-chat",
                body=content,
                ai_interaction_id=interaction.id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            ),
            credits_charged=cost,
        )

    elif body.command == "brainstorm":
        topic = (prompt_text or "").strip()
        if len(topic) < 3:
            interaction.status = "failed"
            await db.commit()
            await release_reservation(reservation_id, "invalid_input", http)
            raise HTTPException(status_code=400, detail="Topic must be at least 3 characters")

        try:
            content, input_tokens, output_tokens = await _handle_brainstorm(topic, user_id, http)
        except Exception as exc:
            interaction.status = "failed"
            interaction.failure_reason = str(exc)
            await db.commit()
            await release_reservation(reservation_id, "openai_error", http)
            raise HTTPException(status_code=500, detail="Brainstorm failed. Credits refunded.")

        interaction.status = "completed"
        interaction.input_tokens = input_tokens
        interaction.output_tokens = output_tokens
        interaction.completed_at = datetime.now(timezone.utc)
        await db.commit()
        await commit_reservation(reservation_id, http)

        from app.schemas.commands import AITextResult
        return CommandSyncResponse(
            ai_interaction_id=interaction.id,
            command="brainstorm",
            result=AITextResult(command="brainstorm", body=content, ai_interaction_id=interaction.id),
            credits_charged=cost,
        )

    elif body.command == "palette":
        description = (prompt_text or "").strip()
        if not description:
            interaction.status = "failed"
            await db.commit()
            await release_reservation(reservation_id, "invalid_input", http)
            raise HTTPException(status_code=400, detail="Description is required for /palette")

        content = ""
        input_tokens = output_tokens = 0
        last_exc = None
        for _attempt in range(2):
            try:
                content, input_tokens, output_tokens = await _handle_palette(description)
                colors = json.loads(content)
                if not isinstance(colors, list) or len(colors) != 5:
                    raise ValueError("Expected exactly 5 colors")
                break
            except (json.JSONDecodeError, ValueError) as exc:
                last_exc = exc
                continue

        if not content or last_exc:
            interaction.status = "failed"
            await db.commit()
            await release_reservation(reservation_id, "palette_parse_error", http)
            raise HTTPException(status_code=500, detail="Palette generation failed. Credits refunded.")

        colors_parsed = json.loads(content)
        interaction.status = "completed"
        interaction.input_tokens = input_tokens
        interaction.output_tokens = output_tokens
        interaction.completed_at = datetime.now(timezone.utc)
        await db.commit()
        await commit_reservation(reservation_id, http)

        from app.schemas.commands import AIPaletteResult, AIPaletteColor
        return CommandSyncResponse(
            ai_interaction_id=interaction.id,
            command="palette",
            result=AIPaletteResult(
                colors=[AIPaletteColor(**c) for c in colors_parsed],
                ai_interaction_id=interaction.id,
            ),
            credits_charged=cost,
        )

    # ---------------------------------------------------------------------------
    # Async commands (mockup-image, mockup-audio)
    # ---------------------------------------------------------------------------

    elif body.command in ("mockup-image", "mockup-audio"):
        prompt = (prompt_text or "").strip()
        if not prompt:
            interaction.status = "failed"
            await db.commit()
            await release_reservation(reservation_id, "invalid_input", http)
            raise HTTPException(
                status_code=400,
                detail=f"Please include a prompt after `/{body.command}`",
            )

        kind = "image" if body.command == "mockup-image" else "audio"
        estimated = 45 if kind == "image" else 30

        asset = MockupAsset(
            replicate_prediction_id="pending",  # updated by Celery task after enqueue
            kind=kind,
            s3_key="",
            watermark_meta={},
        )
        db.add(asset)
        await db.flush()

        interaction.mockup_asset_id = asset.id
        await db.commit()

        webhook_url = f"{settings.replicate_webhook_url}"

        if kind == "image":
            from app.workers.generation_tasks import enqueue_image_prediction
            enqueue_image_prediction.delay(
                str(interaction.id),
                str(asset.id),
                prompt,
                tier,
                webhook_url,
            )
        else:
            from app.workers.generation_tasks import enqueue_audio_prediction
            enqueue_audio_prediction.delay(
                str(interaction.id),
                str(asset.id),
                prompt,
                tier,
                webhook_url,
            )

        return CommandAsyncResponse(
            ai_interaction_id=interaction.id,
            mockup_asset_id=asset.id,
            status="queued",
            estimated_seconds=estimated,
        )

    raise HTTPException(status_code=400, detail=f"Unknown command: {body.command}")
