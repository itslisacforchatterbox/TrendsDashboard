"""Pydantic data models for typed pipeline stages, artist-tailored recommendations, and schema validation."""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field
from src.config import (
    PLATFORM_LITERAL,
    STATUS_LITERAL,
    TREND_NATURE_LITERAL,
    TYPE_LITERAL,
)


class RawItem(BaseModel):
    """Raw scraped record from any external platform, API, or RSS feed."""

    source: str
    raw_text: str
    url: str


class ArtistProfile(BaseModel):
    """Rich artist profile compiled from SongStats, Spotify, Instagram, and TikTok."""

    songstats_id: str
    name: str
    genres: List[str]
    bio: str
    brand_identity: str
    top_tracks: List[str]
    musical_profile: str
    primary_channels: List[str]
    recent_content_themes: List[str]


class ExtractedTrend(BaseModel):
    """Structured, actionable music trend tailored specifically for roster artists."""

    trend_name: str = Field(
        ...,
        description="Concise, recognizable title of the trend (e.g. 'Late-Night Vocal Car Confession').",
    )
    trend_summary: str = Field(
        ...,
        description="2-3 sentences explaining creator behavior, origins, visual tone, and audience appeal.",
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
        description="Comma-separated list of musical genres that authentically fit this trend.",
    )
    status: STATUS_LITERAL = Field(
        ...,
        description="Initial lifecycle status: 'Active' for viral audio, 'Idea' for video topics, or '💡 Evergreen' for timeless formats.",
    )
    trend_nature: TREND_NATURE_LITERAL = Field(
        ...,
        description=(
            "Set to 'Evergreen_Format' ONLY if this is a timeless, established industry format that artists execute "
            "using their OWN original music (e.g., raw acoustic room takes, unreleased snippet car teasers, open-verse duets). "
            "Set to 'Temporal_Wave' for audio memes, temporary transition trends, cosplay challenges, or charting radio songs."
        ),
    )
    target_artists: List[str] = Field(
        default_factory=list,
        description="Names of the specific artists from our roster who should execute this trend (e.g. ['K.LAW', 'Allira']).",
    )
    artist_fit_reasoning: str = Field(
        ...,
        description="1-2 sentences explaining WHY this specific trend matches the targeted artist's current era, sound, and visual identity.",
    )
    example_link: str = Field(
        ...,
        description="Direct URL to representative video, audio page, or source article.",
    )
    how_to_execute_it: str = Field(
        ...,
        description="Actionable 1-sentence tactical prompt telling the artist exactly what to film or perform.",
    )
    hashtags_or_keywords: str = Field(
        "",
        description="Space-separated hashtags or keywords.",
    )
    notes: str = Field(
        "",
        description="A&R marketing considerations, pacing notes, or positioning advice.",
    )


class TrendBatch(BaseModel):
    trends: List[ExtractedTrend] = Field(default_factory=list)


class UnifiedTrendResponse(BaseModel):
    """Unified single-call response schema containing curated trends partitioned by platform."""

    tiktok_trends: List[ExtractedTrend] = Field(
        default_factory=list,
        description="Top 3 to 4 trends curated strictly from the TikTok candidates.",
    )
    youtube_trends: List[ExtractedTrend] = Field(
        default_factory=list,
        description="Top 3 to 4 trends curated strictly from the YouTube candidates.",
    )
    spotify_trends: List[ExtractedTrend] = Field(
        default_factory=list,
        description="Top 3 to 4 trends curated strictly from the Spotify candidates.",
    )
    editorial_trends: List[ExtractedTrend] = Field(
        default_factory=list,
        description="Top 1 to 2 trends curated from editorial blogs and newsletters.",
    )

    def all_trends(self) -> List[ExtractedTrend]:
        return (
            self.tiktok_trends
            + self.youtube_trends
            + self.spotify_trends
            + self.editorial_trends
        )