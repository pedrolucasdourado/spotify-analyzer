"""Carga e consulta do dataset.

Todo acesso a dado passa por aqui. É o único lugar que sabe que existe um
Parquet — trocar por DuckDB, SQLite ou banco de verdade depois não toca
nem os routers nem o front.
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import settings
from .contract import ACTIVE_MAX_DAYS_SINCE_SEEN, GLOBAL_MARKET, country_name
from .labels import tier_for
from .validation import validate_or_raise

#: Colunas que a lista pode ordenar. Fechado de propósito: evita ordenação
#: por coluna arbitrária vinda da query string.
SORTABLE = {
    "score": "recommend_score",
    "streams": "total_streams",
    "tracks": "total_tracks",
    "best_rank": "best_rank",
    "days_on_chart": "days_on_chart_total",
    "listeners": "monthly_listeners",
    "name": "artist_name",
    "recency": "days_since_last_seen",
}


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    ).lower()


def _clean(value: Any) -> Any:
    """Converte tipos numpy/pandas para algo que o JSON aceite."""
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if np.isnan(value) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp, date)):
        return pd.Timestamp(value).date().isoformat()
    if isinstance(value, float) and np.isnan(value):
        return None
    if value is pd.NaT:
        return None
    return value


@dataclass
class Filters:
    country: str
    q: str | None = None
    profiles: list[str] | None = None
    trends: list[str] | None = None
    tiers: list[str] | None = None
    labels: list[str] | None = None
    only_active: bool = True
    min_score: float | None = None
    max_score: float | None = None


class Dataset:
    """Dataset carregado em memória. São ~13 mil linhas — cabe folgado."""

    def __init__(self, df: pd.DataFrame, meta: dict[str, Any]) -> None:
        self.df = df
        self.meta = meta

    # -- construção --------------------------------------------------------

    @classmethod
    def load(cls, dataset_path: Path | None = None, meta_path: Path | None = None) -> "Dataset":
        dataset_path = dataset_path or settings.dataset_path
        meta_path = meta_path or settings.meta_path

        if not dataset_path.exists():
            raise FileNotFoundError(
                f"Dataset não encontrado em {dataset_path}.\n"
                "Gere a semente com:  python -m src.pipeline.seed --out data/api\n"
                "Ou aponte SPOTIFY_DATASET para o Parquet real."
            )

        df = pd.read_parquet(dataset_path)
        df = cls._derive(df)
        validate_or_raise(
            df, source=str(dataset_path), strict_ranges=settings.strict_contract
        )

        meta: dict[str, Any] = {}
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta.setdefault("dataset_version", "desconhecida")
        meta.setdefault("is_fixture", True)
        meta["row_count"] = int(len(df))
        meta["artist_count"] = int(df["artist_uri"].nunique())

        return cls(df, meta)

    @staticmethod
    def _derive(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        for col in ("first_entry_date", "last_seen_date"):
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
        if "tier" not in df.columns:
            df["tier"] = df["recommend_score"].map(tier_for)
        if "is_active" not in df.columns:
            df["is_active"] = df["days_since_last_seen"] <= ACTIVE_MAX_DAYS_SINCE_SEEN
        df["_search"] = df["artist_name"].fillna("").map(_strip_accents)
        return df

    # -- consulta ----------------------------------------------------------

    def apply(self, f: Filters) -> pd.DataFrame:
        d = self.df[self.df["country"] == f.country]

        if f.only_active:
            d = d[d["is_active"]]
        if f.q:
            d = d[d["_search"].str.contains(_strip_accents(f.q), regex=False, na=False)]
        if f.profiles:
            d = d[d["profile"].isin(f.profiles)]
        if f.trends:
            d = d[d["trend_status"].isin(f.trends)]
        if f.tiers:
            d = d[d["tier"].isin(f.tiers)]
        if f.labels:
            d = d[d["label_mode"].isin(f.labels)]
        if f.min_score is not None:
            d = d[d["recommend_score"] >= f.min_score]
        if f.max_score is not None:
            d = d[d["recommend_score"] <= f.max_score]
        return d

    @staticmethod
    def sort(d: pd.DataFrame, sort: str, order: str) -> pd.DataFrame:
        column = SORTABLE.get(sort, "recommend_score")
        ascending = order == "asc"
        # rank e recência são "melhor quando menor": inverter mantém a
        # promessa da UI de que 'desc' significa 'melhores primeiro'
        if column in {"best_rank", "days_since_last_seen"}:
            ascending = not ascending
        return d.sort_values(
            [column, "total_streams"], ascending=[ascending, False], na_position="last"
        )

    def countries_for(self, artist_uri: str) -> pd.DataFrame:
        return self.df[self.df["artist_uri"] == artist_uri].sort_values(
            "total_streams", ascending=False
        )

    def row(self, artist_uri: str, country: str) -> pd.Series | None:
        hit = self.df[(self.df["artist_uri"] == artist_uri) & (self.df["country"] == country)]
        return None if hit.empty else hit.iloc[0]

    # -- utilidades --------------------------------------------------------

    @staticmethod
    def to_records(d: pd.DataFrame) -> list[dict[str, Any]]:
        drop = [c for c in ("_search",) if c in d.columns]
        return [
            {k: _clean(v) for k, v in rec.items()}
            for rec in d.drop(columns=drop).to_dict(orient="records")
        ]

    def labels_in(self, country: str) -> list[str]:
        d = self.df[self.df["country"] == country]
        return sorted(d["label_mode"].dropna().unique().tolist())

    def country_options(self) -> list[dict[str, Any]]:
        """Praças presentes no dataset — o front monta o seletor só com isto.

        O chart mundial vem primeiro; o resto sai em ordem alfabética pelo
        nome, que é o que ajuda quem está digitando para procurar.
        """
        counts = self.df.groupby("country").size().to_dict()
        active = self.df[self.df["is_active"]].groupby("country").size().to_dict()
        options = [
            {
                "code": code,
                "name": country_name(code),
                "artists": int(counts.get(code, 0)),
                "active_artists": int(active.get(code, 0)),
            }
            for code in counts
        ]
        options.sort(key=lambda o: (o["code"] != GLOBAL_MARKET, _strip_accents(o["name"])))
        return options

    @property
    def countries(self) -> set[str]:
        return set(self.df["country"].unique())


_dataset: Dataset | None = None


def get_dataset() -> Dataset:
    if _dataset is None:  # pragma: no cover - protegido pelo lifespan
        raise RuntimeError("Dataset não carregado.")
    return _dataset


def set_dataset(ds: Dataset) -> None:
    global _dataset
    _dataset = ds
