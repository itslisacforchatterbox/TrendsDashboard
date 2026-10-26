"""Pydantic data models for typed pipeline stages, schema validation, and unified extraction."""

from typing import List
from pydantic import BaseModel, Field
from src.config import PLATFORM_LITERAL, STATUS_LITERAL, TYPE_LITERAL


class RawItem(BaseModel):
    """Raw scraped record from any external platform, API, or RSS feed."""

    source: str
    raw_text: str
    url: str


class ExtractedTrend(BaseModel):
    """Structured, actionable music trend parsed by Gemini for independent artists."""

    trend_name: str = Field(
        ...,
        description="Concise, recognizable title of the trend (e.g. 'Drop It Like It's Hot Transition Challenge').",
    )
    trend_summary: str = Field(
        ...,
        description="2-3 sentences explaining creator behavior, origins, aesthetic tone, and context.",
    )
    platform: PLATFORM_LITERAL = Field(
        ...,
        description="Native platform where this trend is exploding or best executed.",
    )
    type: TYPE_LITERAL = Field(
        ...,
        description="Classification of trend vehicle: Sound, Format, Challenge, Topic, or Hashtag.",
    )
    genres: str = Field(
        ...,
        description=(
            "Comma-separated list of genres strictly drawn from the roster categories: "
            "Pop, R&B, Dark R&B, Hip-Hop, Rap, Pop Rap, Trap, Indian Hip-Hop, "
            "R&B/Soul, Soul, House, Dance, Edm, Indie Pop, Afrobeats, or All."
        ),
    )
    status: STATUS_LITERAL = Field(
        ...,
        description="Use 'Active' if currently surging; use 'Idea' if an evergreen format or seasonal concept.",
    )
    example_link: str = Field(
        ...,
        description="Direct URL to representative video, audio page, or source article.",
    )
    how_to_execute_it: str = Field(
        ...,
        description="1-sentence actionable tactical prompt written specifically for an independent musician.",
    )
    hashtags_or_keywords: str = Field(
        "",
        description="Space-separated hashtags or searchable keywords (e.g. '#unreleased #rap #studiohook').",
    )
    notes: str = Field(
        "",
        description="A&R marketing considerations, pacing notes, mixing advice, or audience positioning.",
    )


class TrendBatch(BaseModel):
    """Legacy or fallback container for batch trend lists."""

    trends: List[ExtractedTrend] = Field(default_factory=list)


class UnifiedTrendResponse(BaseModel):
    """Unified single-call response schema containing curated trends partitioned by platform."""

    tiktok_trends: List[ExtractedTrend] = Field(
        default_factory=list,
        description="Top 3 to 5 trends curated strictly from the TikTok candidates.",
    )
    youtube_trends: List[ExtractedTrend] = Field(
        default_factory=list,
        description="Top 3 to 5 trends curated strictly from the YouTube candidates.",
    )
    spotify_trends: List[ExtractedTrend] = Field(
        default_factory=list,
        description="Top 3 to 5 trends curated strictly from the Spotify candidates.",
    )
    editorial_trends: List[ExtractedTrend] = Field(
        default_factory=list,
        description="Top 1 to 2 trends from editorial newsletters/blogs if applicable.",
    )

    def all_trends(self) -> List[ExtractedTrend]:
        """Flattens all platform trends into a single combined list for matching and syncing."""
        return (
            self.tiktok_trends
            + self.youtube_trends
            + self.spotify_trends
            + self.editorial_trends
        )