"""Exercita o pipeline sem depender dos CSVs de 10 GB.

Cobre tudo menos a ingestão Dask (`load_features`): clustering, modelo
supervisionado, checagens de sanidade e export. É o que garante que, quando
o dataset real chegar, o script roda — em vez de descobrir um erro de digitação
depois de três horas de processamento.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "api"))
sys.path.insert(0, str(ROOT))

from app.contract import PROFILES, REQUIRED_COLUMNS, TREND_STATUSES  # noqa: E402
from app.validation import validate  # noqa: E402
from src.pipeline import build_dataset as bd  # noqa: E402
from src.pipeline.seed import build_seed  # noqa: E402

#: Colunas que o estágio 00 entrega — o resto é produzido pelos modelos.
STAGE_00_COLUMNS = [
    "artist_uri", "artist_name", "country", "total_tracks", "total_streams",
    "avg_rank", "best_rank", "days_on_chart_total", "first_entry_date",
    "last_seen_date", "entry_count", "label_mode", "stream_concentration",
    "trend_30d", "trend_90d", "days_since_last_seen", "monthly_listeners",
    "peak_listeners", "listener_ratio", "merged_uris_count",
]


@pytest.fixture(scope="module")
def features() -> pd.DataFrame:
    return build_seed(rows=3000, random_state=7)[STAGE_00_COLUMNS]


@pytest.fixture(scope="module")
def clustered(features: pd.DataFrame, tmp_path_factory) -> pd.DataFrame:
    return bd.build_clusters(features, tmp_path_factory.mktemp("models"))


def test_clusters_nomeiam_os_cinco_perfis(clustered: pd.DataFrame):
    assert set(clustered["profile"].unique()) == set(PROFILES)
    assert clustered["profile"].notna().all()


def test_perfis_concentrados_sao_os_de_hit_unico(clustered: pd.DataFrame):
    media = clustered.groupby("profile")["stream_concentration"].mean()
    assert media["One-Hit Wonder"] >= 0.8
    assert media["Efemero Cauda Longa"] >= 0.8
    assert media["Veterano Consistente"] < 0.8


def test_veterano_e_o_maior_em_escala(clustered: pd.DataFrame):
    """O nome vem do centroide; se a ordenação por escala quebrar, um
    veterano vira efêmero — já aconteceu uma vez no notebook."""
    streams = clustered.groupby("profile")["total_streams"].median()
    assert streams["Veterano Consistente"] > streams["Consolidado"]
    assert streams["Consolidado"] > streams["Nicho Recorrente"]


def test_trend_status_fica_no_dominio(clustered: pd.DataFrame):
    assert set(clustered["trend_status"].unique()) <= set(TREND_STATUSES)


def test_modelo_de_clustering_e_persistido(features: pd.DataFrame, tmp_path: Path):
    import joblib

    bd.build_clusters(features, tmp_path)
    blob = joblib.load(tmp_path / "clustering.joblib")
    assert {"scaler", "kmeans", "cluster_names", "features"} <= set(blob)
    assert len(blob["cluster_names"]) == 5


@pytest.fixture(scope="module")
def scored(clustered: pd.DataFrame, tmp_path_factory):
    models_dir = tmp_path_factory.mktemp("models2")
    df, metrics = bd.build_scores(clustered, models_dir)
    return df, metrics, models_dir


def test_score_sai_em_zero_a_cem(scored):
    df, _, _ = scored
    assert df["recommend_score"].between(0, 100).all()


def test_alvo_usa_a_regra_de_percentil_do_pais(scored):
    df, _, _ = scored
    high = df[df["recommend_label"] == "high"]
    assert (high["days_since_last_seen"] <= 90).all()
    low = df[df["recommend_label"] == "low"]
    assert (low["days_since_last_seen"] > 180).all()


def test_metricas_sao_reportadas(scored):
    _, metrics, _ = scored
    for key in ("rf_f1_macro_test", "rf_cv_f1_macro", "high_precision_test", "medium_f1_test"):
        assert 0.0 <= metrics[key] <= 1.0


def test_features_do_modelo_nao_tem_vazamento(scored):
    """As colunas que definem o alvo não podem entrar como preditoras.

    Foi o bug que produzia F1 = 1,00 na primeira versão do notebook 02.
    """
    import joblib

    _, _, models_dir = scored
    cols = joblib.load(models_dir / "recommender.joblib")["feature_cols"]
    proibidas = {"days_since_last_seen", "avg_rank", "best_rank", "trend_30d",
                 "trend_90d", "streams_pct", "recommend_label"}
    assert not (set(cols) & proibidas)


def test_export_cumpre_o_contrato_da_api(scored, tmp_path: Path):
    df, metrics, _ = scored
    bd.export(df, metrics, tmp_path, version="teste-0")

    saved = pd.read_parquet(tmp_path / "artists.parquet")
    assert list(saved.columns) == list(REQUIRED_COLUMNS)
    assert validate(saved) == []

    meta = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    assert meta["is_fixture"] is False
    assert meta["dataset_version"] == "teste-0"
    assert meta["row_count"] == len(saved)
    assert meta["model_metrics"]["rf_f1_macro_test"] == metrics["rf_f1_macro_test"]


def test_sanity_check_reclama_de_base_pequena(scored):
    df, _, _ = scored
    with pytest.raises(RuntimeError, match="linhas"):
        bd.sanity_checks(df.head(50), min_rows=1_000)


def test_sanity_check_passa_na_base_de_teste(scored):
    df, _, _ = scored
    bd.sanity_checks(df, expected_markets=df["country"].nunique(), min_rows=1_000)


def test_sanity_check_reclama_de_praca_faltando(scored):
    df, _, _ = scored
    with pytest.raises(RuntimeError, match="esperava"):
        bd.sanity_checks(
            df[df["country"] != "ar"],
            expected_markets=df["country"].nunique(),
            min_rows=1_000,
        )


def test_consolidacao_de_perfis_duplicados():
    """Dois artist_uri com o mesmo nome na mesma praça viram uma linha."""
    base = dict(
        avg_rank=100.0, best_rank=5.0, first_entry_date=pd.Timestamp("2020-01-01"),
        last_seen_date=pd.Timestamp("2026-05-28"), entry_count=3, label_mode="X",
        stream_concentration=0.3, trend_30d=0.1, trend_90d=0.1,
        monthly_listeners=1000.0, peak_listeners=2000.0, listener_ratio=0.5,
    )
    df = pd.DataFrame([
        {"artist_uri": "a", "country": "br", "artist_name": "Fulano",
         "total_tracks": 200, "total_streams": 1e9, "days_on_chart_total": 900.0, **base},
        {"artist_uri": "b", "country": "br", "artist_name": "Fulano",
         "total_tracks": 2, "total_streams": 1e5, "days_on_chart_total": 5.0, **base},
        {"artist_uri": "c", "country": "br", "artist_name": "Sicrano",
         "total_tracks": 10, "total_streams": 1e6, "days_on_chart_total": 40.0, **base},
    ])
    out = bd.consolidate_duplicate_profiles(df)

    fulano = out[out["artist_name"] == "Fulano"]
    assert len(fulano) == 1, "os dois perfis do Fulano tinham que virar uma linha"
    assert fulano.iloc[0]["artist_uri"] == "a", "fica o URI do perfil dominante em streams"
    assert fulano.iloc[0]["total_tracks"] == 202
    assert fulano.iloc[0]["merged_uris_count"] == 2
    assert out[out["artist_name"] == "Sicrano"].iloc[0]["merged_uris_count"] == 1


def test_consolidacao_nunca_agrupa_nome_vazio():
    base = dict(
        avg_rank=100.0, best_rank=5.0, first_entry_date=pd.Timestamp("2020-01-01"),
        last_seen_date=pd.Timestamp("2026-05-28"), entry_count=1, label_mode="X",
        stream_concentration=0.9, trend_30d=0.0, trend_90d=0.0,
        monthly_listeners=None, peak_listeners=None, listener_ratio=None,
        total_tracks=1, total_streams=1e4, days_on_chart_total=2.0,
    )
    df = pd.DataFrame([
        {"artist_uri": "x", "country": "br", "artist_name": None, **base},
        {"artist_uri": "y", "country": "br", "artist_name": None, **base},
    ])
    out = bd.consolidate_duplicate_profiles(df)
    assert len(out) == 2, "nome nulo não pode virar chave de agrupamento"
