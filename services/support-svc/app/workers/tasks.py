"""
support-svc — General Celery tasks.

- embed_kb_article(article_id): embed a KbArticle with text-embedding-3-large
- send_ticket_confirmation_email(ticket_id): enqueue email via notification-svc
- send_ticket_push(ticket_id): enqueue push via notification-svc
- purge_expired_chatbot_sessions(): nightly cleanup
"""

from __future__ import annotations

import json
import logging
import os

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _sync_db_url() -> str:
    return os.environ.get(
        "DATABASE_URL_SYNC",
        os.environ.get(
            "DATABASE_URL", "postgresql://colab:colab@localhost:5432/colab"
        ).replace("postgresql+asyncpg://", "postgresql://"),
    )


def _rabbitmq_url() -> str:
    return os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")


def _emit_event(event_name: str, payload: dict) -> None:
    """Best-effort synchronous RabbitMQ publish."""
    try:
        import pika

        params = pika.URLParameters(_rabbitmq_url())
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        domain = event_name.split(".")[0]
        channel.exchange_declare(exchange=domain, exchange_type="topic", durable=True)
        channel.basic_publish(
            exchange=domain,
            routing_key=event_name,
            body=json.dumps({"event": event_name, "data": payload}).encode(),
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=2,
            ),
        )
        connection.close()
    except Exception as exc:
        logger.warning("Event emit failed [%s]: %s", event_name, exc)


@celery_app.task(
    name="support.embed_kb_article",
    queue="support-default",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
)
def embed_kb_article(article_id: str) -> dict:
    """
    Embed a KbArticle's body_md with text-embedding-3-large and store the result.

    Called after article create or update (T-003).
    """
    import os

    from openai import OpenAI
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    db_url = _sync_db_url()
    openai_key = os.environ.get("SUPPORT_OPENAI_API_KEY", "")
    embed_model = os.environ.get("SUPPORT_OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")

    if not openai_key:
        logger.warning("SUPPORT_OPENAI_API_KEY not set; skipping embedding for %s", article_id)
        return {"skipped": True}

    engine = create_engine(db_url, pool_pre_ping=True)
    try:
        with Session(engine) as sess:
            row = sess.execute(
                text("SELECT body_md FROM support.kb_article WHERE id = :id"),
                {"id": article_id},
            ).fetchone()

            if row is None:
                logger.warning("KbArticle %s not found; skipping embed", article_id)
                return {"skipped": True}

            body_md: str = row.body_md

            client = OpenAI(api_key=openai_key)
            resp = client.embeddings.create(
                model=embed_model,
                input=body_md[:8000],  # safe truncation
            )
            embedding = resp.data[0].embedding
            embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

            sess.execute(
                text(
                    "UPDATE support.kb_article SET embedding = CAST(:emb AS vector) WHERE id = :id"
                ),
                {"emb": embedding_str, "id": article_id},
            )
            sess.commit()
    finally:
        engine.dispose()

    logger.info("Embedded KbArticle %s", article_id)
    return {"article_id": article_id, "embedded": True}


@celery_app.task(
    name="support.send_ticket_confirmation_email",
    queue="support-default",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
)
def send_ticket_confirmation_email(ticket_id: str) -> dict:
    """Emit RabbitMQ event so notification-svc sends a confirmation email."""
    _emit_event(
        "support.ticket.confirmation_email",
        {"ticket_id": ticket_id},
    )
    return {"ticket_id": ticket_id, "emitted": True}


@celery_app.task(
    name="support.send_ticket_push",
    queue="support-default",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
)
def send_ticket_push(ticket_id: str) -> dict:
    """Emit RabbitMQ event so notification-svc sends a push notification."""
    _emit_event(
        "support.ticket.confirmation_push",
        {"ticket_id": ticket_id},
    )
    return {"ticket_id": ticket_id, "emitted": True}


@celery_app.task(name="support.purge_expired_chatbot_sessions", queue="support-default")
def purge_expired_chatbot_sessions() -> dict:
    """
    Nightly cleanup of expired ChatbotSession rows.
    """
    from datetime import datetime, timezone

    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    db_url = _sync_db_url()
    engine = create_engine(db_url, pool_pre_ping=True)
    now = datetime.now(tz=timezone.utc)

    try:
        with Session(engine) as sess:
            result = sess.execute(
                text(
                    "DELETE FROM support.chatbot_session WHERE expires_at < :now"
                ),
                {"now": now},
            )
            sess.commit()
            deleted = result.rowcount
    finally:
        engine.dispose()

    logger.info("Purged %d expired chatbot sessions", deleted)
    return {"deleted": deleted}
