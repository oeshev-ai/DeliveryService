"""Схемы FAQ knowledge base."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FaqArticleDTO(BaseModel):
    id: int
    slug: str
    title: str
    category: str
    question: str
    answer: str
    keywords: str = ""
    is_active: bool = True


class FaqArticleCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=64)
    title: str = Field(min_length=2, max_length=256)
    category: str = Field(min_length=2, max_length=64)
    question: str = Field(min_length=2)
    answer: str = Field(min_length=2)
    keywords: str = ""
    is_active: bool = True


class FaqArticleUpdate(BaseModel):
    title: str | None = None
    category: str | None = None
    question: str | None = None
    answer: str | None = None
    keywords: str | None = None
    is_active: bool | None = None


class FaqHitDTO(BaseModel):
    article: FaqArticleDTO
    score: float


class FaqSearchResponse(BaseModel):
    query: str
    hits: list[FaqHitDTO]
    best: FaqHitDTO | None = None


class FaqAskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)


class FaqAskResponse(BaseModel):
    ok: bool
    answer: str
    confidence: float
    source: str  # keyword | llm | none
    article_id: int | None = None
    suggestions: list[FaqArticleDTO] = Field(default_factory=list)
    escalate: bool = False
