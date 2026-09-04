"""Endpoints."""

from __future__ import annotations

import csv
import io
from typing import Annotated, Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from .config import settings
from .contract import PROFILES, TIER_CUTS, TIERS, TREND_STATUSES, country_name
from .dataset import Dataset, Filters, SORTABLE, get_dataset
from .labels import METRIC_LABELS, ROLE_BY_PROFILE, TIER_INFO, TREND_LABEL, readings, role_for
from .schemas import (
    ArtistDetail,
    ArtistListItem,
    Health,
    MarketOverview,
    MetaResponse,
    Page,
    Presence,
)

router = APIRouter()

DISCLAIMER = (
    "Streams indicam relevância, não garantem público pagante em show. "
    "O score é a probabilidade de o artista atender a uma regra de negócio "
    "sobre os charts, não uma previsão de bilheteria."
)

DatasetDep = Annotated[Dataset, Depends(get_dataset)]


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _as_list_item(rec: dict[str, Any]) -> ArtistListItem:
    return ArtistListItem(
        **{k: rec[k] for k in (
            "artist_uri", "artist_name", "country", "recommend_score", "tier",
            "profile", "trend_status", "is_active", "total_streams", "total_tracks",
            "entry_count", "best_rank", "days_on_chart_total", "stream_concentration",
            "country_stream_share", "listener_ratio", "monthly_listeners",
            "label_mode", "days_since_last_seen",
        )},
        tier_label=TIER_INFO[rec["tier"]]["label"],
        role=role_for(rec["profile"])["role"],
        trend_label=TREND_LABEL.get(rec["trend_status"], rec["trend_status"]),
    )


def _validate_country(ds: Dataset, country: str) -> str:
    """A lista de praças vem do dataset, não de uma constante no código."""
    country = country.strip().lower()
    if country not in ds.countries:
        disponiveis = sorted(ds.countries)
        amostra = ", ".join(disponiveis[:8])
        raise HTTPException(
            status_code=422,
            detail=(
                f"Praça '{country}' não existe na base. "
                f"São {len(disponiveis)} disponíveis ({amostra}…) — veja a lista completa em /meta."
            ),
        )
    return country


def _validate_domain(values: list[str] | None, allowed: tuple[str, ...], field: str) -> list[str] | None:
    if not values:
        return None
    unknown = [v for v in values if v not in allowed]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"{field} inválido: {', '.join(unknown)}. Aceitos: {', '.join(allowed)}.",
        )
    return values


def _counts(d: pd.DataFrame, column: str, label_map: dict[str, str] | None = None,
            order: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    raw = d[column].value_counts().to_dict()
    keys = order or tuple(sorted(raw))
    return [
        {"value": k, "label": (label_map or {}).get(k, k), "count": int(raw.get(k, 0))}
        for k in keys
    ]


# --------------------------------------------------------------------------
# health / meta
# --------------------------------------------------------------------------


@router.get("/health", response_model=Health, tags=["sistema"])
def health(ds: DatasetDep) -> Health:
    return Health(
        status="ok",
        dataset_version=str(ds.meta.get("dataset_version")),
        is_fixture=bool(ds.meta.get("is_fixture", True)),
        rows=int(len(ds.df)),
    )


@router.get("/meta", response_model=MetaResponse, tags=["sistema"])
def meta(ds: DatasetDep) -> MetaResponse:
    """Tudo que o front precisa para montar filtros e avisos.

    A interface não guarda nenhuma lista fixa: praças, perfis, momentos e
    faixas saem daqui.
    """
    return MetaResponse(
        dataset_version=str(ds.meta.get("dataset_version")),
        is_fixture=bool(ds.meta.get("is_fixture", True)),
        fixture_notice=ds.meta.get("fixture_notice"),
        reference_date=ds.meta.get("reference_date"),
        window_start=ds.meta.get("window_start"),
        window_end=ds.meta.get("window_end"),
        row_count=int(ds.meta["row_count"]),
        artist_count=int(ds.meta["artist_count"]),
        countries=ds.country_options(),
        profiles=[
            {"value": p, "label": p, "role": ROLE_BY_PROFILE[p]["role"],
             "note": ROLE_BY_PROFILE[p]["note"]}
            for p in PROFILES
        ],
        trends=[{"value": t, "label": TREND_LABEL[t]} for t in TREND_STATUSES],
        tiers=[
            {"value": name, "label": TIER_INFO[name]["label"],
             "note": TIER_INFO[name]["note"], "min_score": cut}
            for name, cut in TIER_CUTS
        ],
        sort_options=[
            {"value": "score", "label": "Score do modelo"},
            {"value": "streams", "label": "Streams na janela"},
            {"value": "days_on_chart", "label": "Tempo de estrada no chart"},
            {"value": "best_rank", "label": "Melhor posição"},
            {"value": "listeners", "label": "Ouvintes mensais (global)"},
            {"value": "recency", "label": "Aparição mais recente"},
            {"value": "name", "label": "Nome"},
        ],
        model_metrics={k: float(v) for k, v in (ds.meta.get("model_metrics") or {}).items()},
        model_used_for_score=ds.meta.get("model_used_for_score"),
        disclaimer=DISCLAIMER,
    )


# --------------------------------------------------------------------------
# artistas
# --------------------------------------------------------------------------


CountryQ = Annotated[str, Query(
    description="Praça do evento: código ISO de 2 letras, ou 'global'. Lista completa em /meta."
)]
ProfileQ = Annotated[list[str] | None, Query(description="Perfil de carreira; repita para vários")]
TrendQ = Annotated[list[str] | None, Query(description="Momento do artista; repita para vários")]
TierQ = Annotated[list[str] | None, Query(description="Faixa de aposta; repita para várias")]
LabelQ = Annotated[list[str] | None, Query(description="Gravadora predominante")]


def _filters(
    ds: DatasetDep,
    country: CountryQ,
    q: Annotated[str | None, Query(description="Busca por nome, sem acento e sem caixa")] = None,
    profile: ProfileQ = None,
    trend: TrendQ = None,
    tier: TierQ = None,
    label: LabelQ = None,
    only_active: Annotated[bool, Query(description="Só quem apareceu no chart nos últimos 90 dias")] = True,
    min_score: Annotated[float | None, Query(ge=0, le=100)] = None,
    max_score: Annotated[float | None, Query(ge=0, le=100)] = None,
) -> Filters:
    return Filters(
        country=_validate_country(ds, country),
        q=q,
        profiles=_validate_domain(profile, PROFILES, "profile"),
        trends=_validate_domain(trend, TREND_STATUSES, "trend"),
        tiers=_validate_domain(tier, TIERS, "tier"),
        labels=label or None,
        only_active=only_active,
        min_score=min_score,
        max_score=max_score,
    )


FiltersDep = Annotated[Filters, Depends(_filters)]


@router.get("/artists", response_model=Page, tags=["artistas"])
def list_artists(
    ds: DatasetDep,
    filters: FiltersDep,
    sort: Annotated[str, Query(description=f"Um de: {', '.join(SORTABLE)}")] = "score",
    order: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
    limit: Annotated[int, Query(ge=1)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page:
    if sort not in SORTABLE:
        raise HTTPException(
            status_code=422,
            detail=f"sort inválido: '{sort}'. Aceitos: {', '.join(SORTABLE)}.",
        )
    limit = min(limit, settings.max_page_size)

    d = ds.apply(filters)
    total = int(len(d))
    page = ds.sort(d, sort, order).iloc[offset: offset + limit]
    return Page(
        total=total,
        limit=limit,
        offset=offset,
        items=[_as_list_item(r) for r in Dataset.to_records(page)],
    )


@router.get("/artists/{artist_uri}", response_model=ArtistDetail, tags=["artistas"])
def artist_detail(
    ds: DatasetDep,
    artist_uri: str,
    country: CountryQ,
) -> ArtistDetail:
    country = _validate_country(ds, country)
    row = ds.row(artist_uri, country)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Artista não encontrado na praça {country.upper()}.",
        )
    rec = Dataset.to_records(row.to_frame().T)[0]
    base = _as_list_item(rec)

    return ArtistDetail(
        **base.model_dump(),
        avg_rank=rec["avg_rank"],
        peak_listeners=rec["peak_listeners"],
        first_entry_date=rec["first_entry_date"],
        last_seen_date=rec["last_seen_date"],
        merged_uris_count=rec["merged_uris_count"],
        cluster=rec["cluster"],
        recommend_label=rec["recommend_label"],
        role_note=role_for(rec["profile"])["note"],
        tier_note=TIER_INFO[rec["tier"]]["note"],
        readings=readings(rec),
        presence=[
            Presence(
                country=p["country"],
                country_name=country_name(p["country"]),
                recommend_score=p["recommend_score"],
                tier=p["tier"],
                tier_label=TIER_INFO[p["tier"]]["label"],
                profile=p["profile"],
                role=role_for(p["profile"])["role"],
                total_streams=p["total_streams"],
                country_stream_share=p["country_stream_share"],
                is_active=p["is_active"],
            )
            for p in Dataset.to_records(ds.countries_for(artist_uri))
        ],
    )


@router.get("/artists/{artist_uri}/countries", response_model=list[Presence], tags=["artistas"])
def artist_countries(ds: DatasetDep, artist_uri: str) -> list[Presence]:
    """Leitura de rota: como o mesmo artista se comporta nas cinco praças."""
    rows = Dataset.to_records(ds.countries_for(artist_uri))
    if not rows:
        raise HTTPException(status_code=404, detail="Artista não encontrado.")
    return [
        Presence(
            country=p["country"],
            country_name=country_name(p["country"]),
            recommend_score=p["recommend_score"],
            tier=p["tier"],
            tier_label=TIER_INFO[p["tier"]]["label"],
            profile=p["profile"],
            role=role_for(p["profile"])["role"],
            total_streams=p["total_streams"],
            country_stream_share=p["country_stream_share"],
            is_active=p["is_active"],
        )
        for p in rows
    ]


# --------------------------------------------------------------------------
# praça
# --------------------------------------------------------------------------


@router.get("/markets/{country}/overview", response_model=MarketOverview, tags=["praça"])
def market_overview(ds: DatasetDep, country: str) -> MarketOverview:
    country = _validate_country(ds, country)
    d = ds.df[ds.df["country"] == country]
    active = d[d["is_active"]]

    top_labels = (
        d.groupby("label_mode")["total_streams"].sum().nlargest(8).reset_index()
        .rename(columns={"label_mode": "label", "total_streams": "streams"})
    )
    top_labels["artists"] = [int((d["label_mode"] == lb).sum()) for lb in top_labels["label"]]

    top = ds.sort(active if len(active) else d, "score", "desc").head(10)

    return MarketOverview(
        country=country,
        country_name=country_name(country),
        artists=int(len(d)),
        active_artists=int(len(active)),
        total_streams=float(d["total_streams"].sum()),
        median_streams_active=float(active["total_streams"].median()) if len(active) else None,
        profiles=_counts(d, "profile", order=PROFILES),
        trends=_counts(d, "trend_status", TREND_LABEL, order=TREND_STATUSES),
        tiers=_counts(d, "tier", {k: v["label"] for k, v in TIER_INFO.items()}, order=TIERS),
        top_labels=top_labels.to_dict(orient="records"),
        top_artists=[_as_list_item(r) for r in Dataset.to_records(top)],
    )


# --------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------

EXPORT_COLUMNS: list[tuple[str, str]] = [
    ("artist_name", "Artista"),
    ("country", "Praça"),
    ("recommend_score", METRIC_LABELS["recommend_score"]),
    ("tier_label", "Faixa de aposta"),
    ("role", "Papel sugerido no cartaz"),
    ("profile", "Perfil de carreira"),
    ("trend_label", "Momento"),
    ("total_streams", METRIC_LABELS["total_streams"]),
    ("total_tracks", METRIC_LABELS["total_tracks"]),
    ("entry_count", METRIC_LABELS["entry_count"]),
    ("best_rank", METRIC_LABELS["best_rank"]),
    ("days_on_chart_total", METRIC_LABELS["days_on_chart_total"]),
    ("stream_concentration", METRIC_LABELS["stream_concentration"]),
    ("country_stream_share", METRIC_LABELS["country_stream_share"]),
    ("listener_ratio", METRIC_LABELS["listener_ratio"]),
    ("monthly_listeners", METRIC_LABELS["monthly_listeners"]),
    ("days_since_last_seen", METRIC_LABELS["days_since_last_seen"]),
    ("label_mode", METRIC_LABELS["label_mode"]),
    ("artist_uri", "URI Spotify"),
]


@router.get("/export/artists.csv", tags=["export"])
def export_csv(
    ds: DatasetDep,
    filters: FiltersDep,
    sort: str = "score",
    order: str = "desc",
    uris: Annotated[list[str] | None, Query(description="Restringe a estes artistas (lista curta)")] = None,
) -> StreamingResponse:
    """Mesmos filtros de /artists, em CSV com cabeçalhos em português.

    É o arquivo que a produtora leva para a reunião — por isso os rótulos
    são os mesmos que aparecem na tela, não os nomes das colunas técnicas.
    """
    d = ds.apply(filters)
    if uris:
        d = d[d["artist_uri"].isin(uris)]
    d = ds.sort(d, sort if sort in SORTABLE else "score", order).head(settings.max_export_rows)

    buffer = io.StringIO()
    buffer.write("﻿")  # BOM: o Excel em pt-BR precisa disso para os acentos
    writer = csv.writer(buffer, delimiter=";", lineterminator="\n")
    writer.writerow([header for _, header in EXPORT_COLUMNS])

    for rec in Dataset.to_records(d):
        item = _as_list_item(rec).model_dump()
        row = []
        for key, _ in EXPORT_COLUMNS:
            value = item.get(key, rec.get(key))
            if value is None:
                row.append("")
            elif key in {"recommend_score", "stream_concentration", "country_stream_share", "listener_ratio"}:
                row.append(f"{float(value):.4f}".replace(".", ","))
            elif isinstance(value, float):
                row.append(f"{value:.0f}")
            else:
                row.append(value)
        writer.writerow(row)

    buffer.seek(0)
    stamp = ds.meta.get("reference_date", "")
    filename = f"radar-lineup-{filters.country}-{stamp}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
