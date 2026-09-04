"""Schemas de resposta.

`predicted_label` do notebook 02 não aparece em nenhum schema, de
propósito: com F1 entre 0,40 e 0,43 na classe `medium`, a classe prevista
não tem qualidade para ir à tela. Expomos só a probabilidade
(`recommend_score`), traduzida em faixa.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Reading(BaseModel):
    metric: str
    level: str = Field(description="ok | atencao | alerta | info")
    text: str


class ArtistListItem(BaseModel):
    artist_uri: str
    artist_name: str
    country: str
    recommend_score: float
    tier: str
    tier_label: str
    profile: str
    role: str = Field(description="Papel sugerido no cartaz")
    trend_status: str
    trend_label: str
    is_active: bool
    total_streams: float
    total_tracks: int
    entry_count: int
    best_rank: float
    days_on_chart_total: float
    stream_concentration: float
    country_stream_share: float
    listener_ratio: float | None = None
    monthly_listeners: float | None = None
    label_mode: str
    days_since_last_seen: int


class Presence(BaseModel):
    country: str
    country_name: str
    recommend_score: float
    tier: str
    tier_label: str
    profile: str
    role: str
    total_streams: float
    country_stream_share: float
    is_active: bool


class ArtistDetail(ArtistListItem):
    avg_rank: float
    peak_listeners: float | None = None
    first_entry_date: str | None = None
    last_seen_date: str | None = None
    merged_uris_count: int
    cluster: int
    recommend_label: str
    role_note: str
    tier_note: str
    readings: list[Reading]
    presence: list[Presence]


class Page(BaseModel):
    total: int = Field(description="Linhas que passaram nos filtros")
    limit: int
    offset: int
    items: list[ArtistListItem]


class CountOption(BaseModel):
    value: str
    label: str
    count: int


class CountryOption(BaseModel):
    code: str
    name: str
    artists: int
    active_artists: int


class TierOption(BaseModel):
    value: str
    label: str
    note: str
    min_score: float


class MetaResponse(BaseModel):
    dataset_version: str
    is_fixture: bool
    fixture_notice: str | None = None
    reference_date: str | None = None
    window_start: str | None = None
    window_end: str | None = None
    row_count: int
    artist_count: int
    countries: list[CountryOption]
    profiles: list[dict[str, str]]
    trends: list[dict[str, str]]
    tiers: list[TierOption]
    sort_options: list[dict[str, str]]
    model_metrics: dict[str, float] = {}
    model_used_for_score: str | None = None
    disclaimer: str


class MarketOverview(BaseModel):
    country: str
    country_name: str
    artists: int
    active_artists: int
    total_streams: float
    median_streams_active: float | None = None
    profiles: list[CountOption]
    trends: list[CountOption]
    tiers: list[CountOption]
    top_labels: list[dict[str, Any]]
    top_artists: list[ArtistListItem]


class Health(BaseModel):
    status: str
    dataset_version: str
    is_fixture: bool
    rows: int
