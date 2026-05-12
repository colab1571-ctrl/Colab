"""
support-svc — FAQ / KbArticle endpoints.

GET /v1/support/faq           list all articles (public)
GET /v1/support/faq/{slug}    single article     (public)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import KbArticle
from app.schemas import KbArticleListOut, KbArticleOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/support/faq", tags=["faq"])


@router.get("", response_model=KbArticleListOut)
async def list_faq(
    tag: str | None = Query(None, description="Filter by tag"),
    q: str | None = Query(None, description="Full-text search in title/body"),
    db: AsyncSession = Depends(get_db),
) -> KbArticleListOut:
    """List all FAQ articles, optionally filtered by tag or full-text query."""
    stmt = select(KbArticle)

    if tag:
        stmt = stmt.where(KbArticle.tags.any(tag))  # type: ignore[attr-defined]

    if q:
        # Postgres full-text search on title + body
        stmt = stmt.where(
            (KbArticle.title.ilike(f"%{q}%"))  # type: ignore[union-attr]
            | (KbArticle.body_md.ilike(f"%{q}%"))  # type: ignore[union-attr]
        )

    stmt = stmt.order_by(KbArticle.updated_at.desc())  # type: ignore[attr-defined]
    result = await db.execute(stmt)
    articles = result.scalars().all()

    return KbArticleListOut(
        articles=[KbArticleOut.model_validate(a) for a in articles]
    )


@router.get("/{slug}", response_model=KbArticleOut)
async def get_faq_article(
    slug: str,
    db: AsyncSession = Depends(get_db),
) -> KbArticleOut:
    """Fetch a single FAQ article by slug."""
    result = await db.execute(
        select(KbArticle).where(KbArticle.slug == slug)
    )
    article = result.scalar_one_or_none()
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    return KbArticleOut.model_validate(article)
