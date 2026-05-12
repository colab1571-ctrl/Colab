"""
profile-svc — Vocation, skill, and personality quiz endpoints.

PUT /api/v1/profile/me/vocations
PUT /api/v1/profile/me/skills
POST /api/v1/profile/me/personality
GET /api/v1/vocations/taxonomy
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Profile, ProfileVocation, ProfileSkill, PersonalityAnswer, PersonalityQuestion, VocationTaxonomy
from app.schemas.profile import PersonalityResult, PersonalitySubmit, SkillLabel, VocationItem, VocationsPut, SkillsPut
from app.services.personality import score_quiz

router = APIRouter(prefix="/api/v1/profile/me", tags=["vocations"])
taxonomy_router = APIRouter(prefix="/api/v1/vocations", tags=["vocations"])

# 9 locked categories per plan §4
VALID_CATEGORIES = {
    "Visual Arts",
    "Music & Audio",
    "Performing Arts",
    "Film, Video & Animation",
    "Design",
    "Writing & Literature",
    "Digital, Code & New Media",
    "Craft, Fashion & Maker",
    "Producing, Curation & Direction",
}


def _require_auth(request: Request) -> uuid.UUID:
    uid_header = request.headers.get("X-User-Id")
    if not uid_header:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return uuid.UUID(uid_header)


async def _get_profile(user_id: uuid.UUID, session: AsyncSession) -> Profile:
    result = await session.execute(select(Profile).where(Profile.user_id == user_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile


@router.put("/vocations", response_model=list[VocationItem])
async def put_vocations(
    body: VocationsPut,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> list[VocationItem]:
    """
    Replace vocation set. Validates against taxonomy; unknown subtag accepted
    as other:<slug> with flagged_for_review=true.
    Exactly one vocation must have is_primary=true.
    """
    user_id = _require_auth(request)
    profile = await _get_profile(user_id, session)

    primary_count = sum(1 for v in body.vocations if v.is_primary)
    if primary_count == 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Exactly one vocation must be primary")
    if primary_count > 1:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only one vocation can be primary")

    # Validate categories
    for v in body.vocations:
        if v.category not in VALID_CATEGORIES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid vocation category: {v.category!r}. Must be one of: {sorted(VALID_CATEGORIES)}",
            )

    # Load taxonomy for subtag validation
    tax_result = await session.execute(
        select(VocationTaxonomy).where(VocationTaxonomy.is_active == True)
    )
    taxonomy = {(t.category, t.subtag) for t in tax_result.scalars()}

    # Delete existing vocations
    for voc in list(profile.vocations):
        await session.delete(voc)

    # Add new vocations
    new_vocations = []
    for voc_item in body.vocations:
        is_known = (voc_item.category, voc_item.subtag) in taxonomy
        flagged = not is_known

        if not is_known:
            # Normalize unknown as other:<slug>
            slug = voc_item.subtag.lower().replace(" ", "-")[:64]
            subtag = f"other:{slug}"
        else:
            subtag = voc_item.subtag

        voc = ProfileVocation(
            profile_id=profile.id,
            category=voc_item.category,
            subtag=subtag,
            is_primary=voc_item.is_primary,
            flagged_for_review=flagged,
        )
        session.add(voc)
        new_vocations.append(VocationItem(category=voc_item.category, subtag=subtag, is_primary=voc_item.is_primary))

    await session.commit()
    return new_vocations


@router.put("/skills", response_model=list[SkillLabel])
async def put_skills(
    body: SkillsPut,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> list[SkillLabel]:
    """Replace skill set (max 20)."""
    user_id = _require_auth(request)
    profile = await _get_profile(user_id, session)

    # Delete existing skills
    for skill in list(profile.skills):
        await session.delete(skill)

    result_skills = []
    for label in body.labels[:20]:
        if not label.strip():
            continue
        lower = label.lower().strip()[:40]
        skill = ProfileSkill(
            profile_id=profile.id,
            label_raw=label.strip()[:40],
            label_lower=lower,
            label_normalized=None,
        )
        session.add(skill)
        result_skills.append(SkillLabel(label_raw=label.strip()[:40]))

    await session.commit()
    return result_skills


@router.post("/personality", response_model=PersonalityResult)
async def submit_personality_quiz(
    body: PersonalitySubmit,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> PersonalityResult:
    """Score personality quiz, persist answers and archetype."""
    user_id = _require_auth(request)
    profile = await _get_profile(user_id, session)

    # Load active questions
    q_result = await session.execute(
        select(PersonalityQuestion).where(PersonalityQuestion.is_active == True).order_by(PersonalityQuestion.sort_order)
    )
    questions_db = q_result.scalars().all()

    questions = [
        {"question_key": q.question_key, "options": q.options}
        for q in questions_db
    ]

    answers_input = [{"question_key": a.question_key, "answer_key": a.answer_key} for a in body.answers]
    archetype, scores = score_quiz(answers_input, questions)

    # Delete existing answers, persist new
    for ans in list(profile.personality_answers):
        await session.delete(ans)

    for ans in body.answers:
        pa = PersonalityAnswer(
            profile_id=profile.id,
            question_key=ans.question_key,
            answer_key=ans.answer_key,
        )
        session.add(pa)

    profile.personality_archetype = archetype
    await session.commit()

    return PersonalityResult(archetype=archetype, scores=scores)


@taxonomy_router.get("/taxonomy")
async def get_taxonomy(session: AsyncSession = Depends(get_db)) -> dict:
    """Return the active vocation taxonomy grouped by category."""
    result = await session.execute(
        select(VocationTaxonomy)
        .where(VocationTaxonomy.is_active == True)
        .order_by(VocationTaxonomy.category, VocationTaxonomy.sort_order)
    )
    taxonomy_items = result.scalars().all()

    grouped: dict[str, list[dict]] = {}
    for item in taxonomy_items:
        if item.category not in grouped:
            grouped[item.category] = []
        grouped[item.category].append({"subtag": item.subtag, "display": item.display})

    return {"categories": grouped}
