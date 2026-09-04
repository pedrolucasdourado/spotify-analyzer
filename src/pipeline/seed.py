"""Gerador do dataset-semente (fixture).

Existe para destravar API e front enquanto o dataset real está sendo
baixado/reprocessado. Escreve exatamente o mesmo contrato que
`build_dataset.py` vai escrever, então trocar um pelo outro é mudar o
arquivo apontado por SPOTIFY_DATASET — nenhum código muda.

Duas origens de dados:

1. **Âncoras reais.** As saídas impressas nos notebooks contêm linhas
   verdadeiras: o top 10 BR do 00 (streams, faixas, rank, concentração,
   listener_ratio), o top 15 BR do 02 (score, perfil, tendência) e a
   validação de artistas conhecidos do 03 (perfil por praça de Drake,
   Taylor Swift, Bad Bunny, Billie Eilish e Anitta). Essas linhas entram
   com os valores originais.

2. **Preenchimento sintético.** O resto é sorteado a partir dos
   centroides de cluster e das proporções medidas nos notebooks, para
   que filtros, ordenação e paginação sejam exercitados com uma
   distribuição parecida com a real.

`meta.json` sai com `is_fixture: true`; a API expõe essa flag e o front
mostra um aviso permanente. Nenhum número daqui deve ser apresentado
como resultado do projeto.

Uso:
    python -m src.pipeline.seed --out data/api --rows 600
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "api"))

from app.contract import (  # noqa: E402
    ACTIVE_MAX_DAYS_SINCE_SEEN,
    PILOT_COUNTRIES as COUNTRIES,
    PROFILES,
    REQUIRED_COLUMNS,
)
from app.validation import validate_or_raise  # noqa: E402

# --------------------------------------------------------------------------
# Constantes medidas nos notebooks
# --------------------------------------------------------------------------

REFERENCE_DATE = date(2026, 5, 28)  # última data de chart na base (notebook 01)
WINDOW_START = date(2017, 1, 1)

#: Proporção de cada perfil em 13.120 linhas (notebook 03, seção 5).
PROFILE_WEIGHTS = {
    "Veterano Consistente": 185,
    "Consolidado": 1073,
    "Nicho Recorrente": 2814,
    "One-Hit Wonder": 3741,
    "Efemero Cauda Longa": 5307,
}

#: Centroides reais (notebook 03, seção 4) usados como medianas, mais o
#: sigma lognormal que dá a cauda. (mediana, sigma)
PROFILE_PARAMS = {
    "Veterano Consistente": dict(
        tracks=(122.0, 0.45), streams=(2.31e9, 0.60), days_chart=(958.0, 0.20),
        conc=(0.15, 0.05), entries=(101.0, 0.40), best_rank=(1, 6),
        active_p=0.85, score=(94.0, 2.5),
    ),
    "Consolidado": dict(
        tracks=(28.0, 0.60), streams=(4.73e8, 0.80), days_chart=(695.0, 0.35),
        conc=(0.36, 0.10), entries=(23.0, 0.60), best_rank=(1, 28),
        active_p=0.55, score=(84.0, 9.0),
    ),
    "Nicho Recorrente": dict(
        tracks=(6.4, 0.60), streams=(6.08e7, 1.00), days_chart=(168.0, 0.60),
        conc=(0.53, 0.12), entries=(5.3, 0.70), best_rank=(18, 95),
        active_p=0.20, score=(38.0, 13.0),
    ),
    "One-Hit Wonder": dict(
        tracks=(1.8, 0.30), streams=(3.20e7, 1.20), days_chart=(158.0, 0.70),
        conc=(0.95, 0.03), entries=(1.5, 0.40), best_rank=(35, 155),
        active_p=0.10, score=(16.0, 9.0),
    ),
    "Efemero Cauda Longa": dict(
        tracks=(1.17, 0.20), streams=(6.94e5, 1.50), days_chart=(9.0, 0.80),
        conc=(0.96, 0.03), entries=(1.1, 0.30), best_rank=(115, 200),
        active_p=0.045, score=(4.0, 3.5),
    ),
}

#: Entre os artistas ativos: 52% em ascensão, 34% em declínio, 14% estáveis
#: (notebook 03, seção 8: 902 / 584 / 242).
TREND_SPLIT = (0.52, 0.34, 0.14)

#: 25,4% de nulos em monthly_listeners (notebook 02, seção 3).
LISTENER_NULL_RATE = 0.254

LABELS_BY_COUNTRY = {
    "br": ["Som Livre", "Universal Music", "Sony Music", "Warner Music",
           "Workshow", "Independente", "Sky Blue Music", "GR6 Music"],
    "us": ["Republic Records", "Interscope", "Atlantic Records", "Columbia",
           "Def Jam", "RCA Records", "Independente", "Capitol Records"],
    "gb": ["Polydor", "Parlophone", "Island Records", "EMI", "XL Recordings",
           "Independente", "Ministry of Sound", "0207 Def Jam"],
    "mx": ["Fonovisa", "Sony Music Mexico", "Rancho Humilde", "Universal Music",
           "Independente", "Warner Music", "Street Mob Records"],
    "ar": ["Sony Music Argentina", "Dale Play Records", "Warner Music",
           "Independente", "Universal Music", "Grabaciones Sudamerica"],
}

# --------------------------------------------------------------------------
# Âncoras reais lidas das saídas dos notebooks
# --------------------------------------------------------------------------

#: Top 10 BR por total_streams (saída do notebook 00, seção 6).
BR_METRICS = {
    "Henrique & Juliano":  dict(streams=7.213092e9, tracks=212, avg_rank=97.819450, conc=0.042702, ratio=0.846691),
    "Marília Mendonça":    dict(streams=5.288258e9, tracks=171, avg_rank=86.426410, conc=0.044468, ratio=0.793583),
    "Gusttavo Lima":       dict(streams=4.589981e9, tracks=204, avg_rank=84.172691, conc=0.036796, ratio=0.979935),
    "Zé Neto & Cristiano": dict(streams=4.529850e9, tracks=125, avg_rank=84.609811, conc=0.069003, ratio=0.986541),
    "Ana Castela":         dict(streams=4.431963e9, tracks=100, avg_rank=79.898536, conc=0.073503, ratio=0.574158),
    "Jorge & Mateus":      dict(streams=4.389975e9, tracks=125, avg_rank=88.535220, conc=0.049665, ratio=0.853598),
    "MC Ryan SP":          dict(streams=4.369129e9, tracks=152, avg_rank=96.265565, conc=0.069931, ratio=0.864385),
    "Matheus & Kauan":     dict(streams=4.113411e9, tracks=142, avg_rank=84.419006, conc=0.053435, ratio=0.893755),
    "Maiara & Maraisa":    dict(streams=3.016666e9, tracks=121, avg_rank=82.980423, conc=0.077953, ratio=0.677197),
    "Grupo Menos É Mais":  dict(streams=2.913391e9, tracks=56,  avg_rank=93.424321, conc=0.165764, ratio=0.665459),
}

#: Top 15 BR por recommend_score (saída do notebook 02, seção 9).
BR_SCORES = [
    ("Zé Neto & Cristiano", "Veterano Consistente", "Estavel", 97.093861),
    ("Matheus & Kauan", "Veterano Consistente", "Estavel", 96.917726),
    ("Henrique & Juliano", "Veterano Consistente", "Em Declinio", 96.613089),
    ("Jorge & Mateus", "Veterano Consistente", "Estavel", 96.491726),
    ("Marília Mendonça", "Veterano Consistente", "Em Ascensao", 96.440393),
    ("Murilo Huff", "Consolidado", "Em Ascensao", 95.802603),
    ("Maiara & Maraisa", "Veterano Consistente", "Em Ascensao", 95.262004),
    ("Grupo Menos É Mais", "Consolidado", "Em Declinio", 95.060394),
    ("Filipe Ret", "Veterano Consistente", "Em Ascensao", 94.768041),
    ("MC Cabelinho", "Veterano Consistente", "Em Ascensao", 94.540696),
    ("Matuê", "Veterano Consistente", "Em Declinio", 94.429901),
    ("Simone Mendes", "Consolidado", "Em Declinio", 94.369358),
    ("Orochi", "Veterano Consistente", "Estavel", 94.206928),
    ("Alok", "Consolidado", "Inativo", 94.172681),
    ("Ana Castela", "Veterano Consistente", "Em Declinio", 94.102247),
]

#: Perfil por praça (saída do notebook 03, seção 7). Onde o artista tinha
#: mais de uma linha por país, ficamos com o perfil do perfil dominante.
INTERNATIONAL_PROFILES = {
    "Drake": {"ar": "Consolidado", "br": "Consolidado", "gb": "Veterano Consistente",
              "mx": "Consolidado", "us": "Veterano Consistente"},
    "Taylor Swift": {c: "Veterano Consistente" for c in COUNTRIES},
    "Bad Bunny": {"ar": "Veterano Consistente", "br": "Nicho Recorrente",
                  "gb": "Consolidado", "mx": "Veterano Consistente",
                  "us": "Veterano Consistente"},
    "Billie Eilish": {"ar": "Consolidado", "br": "Consolidado",
                      "gb": "Veterano Consistente", "mx": "Consolidado",
                      "us": "Veterano Consistente"},
    "Anitta": {"ar": "Consolidado", "br": "Consolidado", "gb": "Nicho Recorrente",
               "mx": "Consolidado", "us": "Nicho Recorrente"},
}

# --------------------------------------------------------------------------
# Nomes sintéticos — inventados de propósito, para ninguém confundir
# uma linha gerada com um artista real fora das âncoras acima.
# --------------------------------------------------------------------------

NAME_POOLS = {
    "br": (["MC", "DJ", "Grupo", "Banda", ""],
           ["Vialle", "Torrez", "Bruma", "Calixto", "Ravena", "Semprini", "Aldeia",
            "Trindade", "Nordelta", "Cavalgante", "Serrano", "Mirtes", "Boiadeiro",
            "Kaeté", "Vilamar", "Duartte", "Rocinante", "Baruel"]),
    "us": (["", "Lil", "Young", "The"],
           ["Halvorsen", "Nashwood", "Emberly", "Kestrel", "Marrow", "Sableton",
            "Quinlan", "Vessel", "Ardmore", "Northgate", "Palefire", "Wrenlow",
            "Cardigan Sky", "Hollowbrook", "Mavery", "Stonebridge"]),
    "gb": (["", "The"],
           ["Larkmead", "Fennwick", "Brackley", "Ossian", "Cavendish Road",
            "Thornbury", "Halden", "Pemberton", "Grayling", "Ilfracombe",
            "Nettlebed", "Sawbridge", "Kelmscott", "Marlowe Vaughn"]),
    "mx": (["", "Los", "Grupo", "Banda"],
           ["Zacatuche", "Valverde", "Norteño del Sur", "Camarena", "Tepoztli",
            "Ocelote", "Rivas Prieto", "Maravilla", "Cuautla", "Solares",
            "Xochimilco", "Berrones", "Tamaulipa", "Nube Negra"]),
    "ar": (["", "Los", "El"],
           ["Verdolaga", "Pampeano", "Bahiense", "Colastiné", "Rufino Paz",
            "Tandilia", "Zamudio", "Quilmeño", "Lujanera", "Aldao",
            "Chacabuco", "Vidal Roque", "Nahuelito", "Sarandí"]),
}


def _make_name(rng: np.random.Generator, country: str, used: set[str]) -> str:
    prefixes, roots = NAME_POOLS[country]
    for _ in range(200):
        prefix = rng.choice(prefixes)
        root = rng.choice(roots)
        name = f"{prefix} {root}".strip()
        if rng.random() < 0.22:
            name = f"{name} {int(rng.integers(2, 99))}"
        if name not in used:
            used.add(name)
            return name
    # fallback determinístico
    n = len(used)
    name = f"{rng.choice(roots)} {n}"
    used.add(name)
    return name


def _uri(name: str) -> str:
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:22]
    return f"spotify:artist:{digest}"


# --------------------------------------------------------------------------
# Sorteio de uma linha artista x praça
# --------------------------------------------------------------------------


def _lognormal(rng: np.random.Generator, median: float, sigma: float) -> float:
    return float(median * np.exp(rng.normal(0.0, sigma)))


def _draw_activity(rng: np.random.Generator, profile: str) -> tuple[int, float | None]:
    """Devolve (days_since_last_seen, trend_90d)."""
    params = PROFILE_PARAMS[profile]
    if rng.random() < params["active_p"]:
        days = int(rng.integers(0, ACTIVE_MAX_DAYS_SINCE_SEEN + 1))
        roll = rng.random()
        if roll < TREND_SPLIT[0]:
            trend = float(abs(rng.normal(0.9, 0.7)) + 0.2)
        elif roll < TREND_SPLIT[0] + TREND_SPLIT[1]:
            trend = float(-abs(rng.normal(0.45, 0.2)) - 0.2)
        else:
            trend = float(rng.uniform(-0.2, 0.2))
        return days, trend
    # inativo: o notebook 02 registrou trend_90d nulo exatamente na classe low
    days = int(min(3400, 91 + rng.gamma(shape=2.0, scale=430)))
    return days, None


def _trend_status(days_since: int, trend_90d: float | None) -> str:
    """Mesma função do notebook 03, seção 8."""
    recent = days_since <= ACTIVE_MAX_DAYS_SINCE_SEEN
    if recent and trend_90d is not None and trend_90d > 0.2:
        return "Em Ascensao"
    if recent and trend_90d is not None and trend_90d < -0.2:
        return "Em Declinio"
    if recent:
        return "Estavel"
    if days_since <= 365 and trend_90d is not None and trend_90d > 0:
        return "Possivel Retomada"
    return "Inativo"


def _draw_row(
    rng: np.random.Generator,
    name: str,
    country: str,
    profile: str,
    anchor: dict | None = None,
) -> dict:
    p = PROFILE_PARAMS[profile]
    anchor = anchor or {}

    total_tracks = int(max(1, round(anchor.get("tracks", _lognormal(rng, *p["tracks"])))))
    total_streams = float(anchor.get("streams", _lognormal(rng, *p["streams"])))
    days_on_chart = float(max(1.0, min(3400.0, _lognormal(rng, *p["days_chart"]))))
    entry_count = int(max(1, round(_lognormal(rng, *p["entries"]))))
    concentration = float(np.clip(anchor.get("conc", rng.normal(*p["conc"])), 0.01, 1.0))

    best_rank = float(rng.integers(p["best_rank"][0], p["best_rank"][1] + 1))
    if "avg_rank" in anchor:
        avg_rank = float(anchor["avg_rank"])
        best_rank = float(min(best_rank, avg_rank))
    else:
        # a média puxa para o fim do chart quanto maior a cauda de catálogo
        pull = min(0.92, 0.25 + 0.14 * np.log1p(total_tracks))
        avg_rank = float(np.clip(best_rank + pull * (200 - best_rank) * rng.uniform(0.6, 1.0), best_rank, 200))

    days_since, trend_90d = _draw_activity(rng, profile)
    if "trend_status" in anchor:
        # âncora define a tendência; ajustamos recência/trend para ser coerente
        wanted = anchor["trend_status"]
        if wanted == "Inativo":
            days_since, trend_90d = int(min(3400, 200 + rng.gamma(2.0, 400))), None
        else:
            days_since = int(rng.integers(0, ACTIVE_MAX_DAYS_SINCE_SEEN + 1))
            trend_90d = {"Em Ascensao": float(abs(rng.normal(0.9, 0.5)) + 0.25),
                         "Em Declinio": float(-abs(rng.normal(0.45, 0.2)) - 0.25),
                         "Estavel": float(rng.uniform(-0.15, 0.15))}[wanted]

    trend_30d = None if trend_90d is None else float(trend_90d + rng.normal(0, 0.35))

    last_seen = REFERENCE_DATE - timedelta(days=days_since)
    span = int(max(days_on_chart, days_on_chart * rng.uniform(1.0, 2.4)))
    first_entry = max(WINDOW_START, last_seen - timedelta(days=span))
    if first_entry > last_seen:
        first_entry = last_seen

    if rng.random() < LISTENER_NULL_RATE:
        monthly = peak = ratio = None
    else:
        peak_val = float(max(1000.0, total_streams / rng.uniform(35, 140)))
        ratio_val = float(anchor.get("ratio", np.clip(rng.beta(5, 2.2), 0.02, 1.0)))
        monthly = round(peak_val * ratio_val, 0)
        peak = round(peak_val, 0)
        ratio = ratio_val

    if "score" in anchor:
        score = float(anchor["score"])
    else:
        score = float(np.clip(rng.normal(*p["score"]), 0.0, 99.5))

    return {
        "artist_uri": _uri(name),
        "artist_name": name,
        "country": country,
        "total_tracks": total_tracks,
        "total_streams": total_streams,
        "entry_count": entry_count,
        "avg_rank": avg_rank,
        "best_rank": best_rank,
        "days_on_chart_total": days_on_chart,
        "first_entry_date": pd.Timestamp(first_entry),
        "last_seen_date": pd.Timestamp(last_seen),
        "days_since_last_seen": days_since,
        "trend_30d": trend_30d,
        "trend_90d": trend_90d,
        "stream_concentration": concentration,
        "country_stream_share": np.nan,  # calculado depois, entre praças
        "monthly_listeners": monthly,
        "peak_listeners": peak,
        "listener_ratio": ratio,
        "label_mode": str(rng.choice(LABELS_BY_COUNTRY[country])),
        "merged_uris_count": int(1 if rng.random() > 0.0075 else 2),
        "cluster": PROFILES.index(profile),
        "profile": profile,
        "trend_status": _trend_status(days_since, trend_90d),
        "recommend_score": score,
    }


# --------------------------------------------------------------------------
# Montagem
# --------------------------------------------------------------------------


def build_seed(rows: int = 600, random_state: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(random_state)
    records: list[dict] = []
    used_names: set[str] = set()

    profile_names = list(PROFILE_WEIGHTS)
    profile_p = np.array([PROFILE_WEIGHTS[p] for p in profile_names], dtype=float)
    profile_p /= profile_p.sum()

    # --- âncoras reais: top BR do notebook 02 (+ métricas do 00 quando existem)
    for name, profile, trend, score in BR_SCORES:
        anchor: dict = {"score": score, "trend_status": trend}
        if name in BR_METRICS:
            m = BR_METRICS[name]
            anchor.update(tracks=m["tracks"], streams=m["streams"],
                          avg_rank=m["avg_rank"], conc=m["conc"], ratio=m["ratio"])
        records.append(_draw_row(rng, name, "br", profile, anchor))
        used_names.add(name)

    # Gusttavo Lima e MC Ryan SP aparecem no top de streams do 00 mas não no
    # top 15 de score do 02 — entram com as métricas reais e score sorteado.
    for name in ("Gusttavo Lima", "MC Ryan SP"):
        m = BR_METRICS[name]
        records.append(_draw_row(rng, name, "br", "Veterano Consistente",
                                 dict(tracks=m["tracks"], streams=m["streams"],
                                      avg_rank=m["avg_rank"], conc=m["conc"], ratio=m["ratio"])))
        used_names.add(name)

    # --- âncoras reais: artistas internacionais validados no notebook 03
    for name, by_country in INTERNATIONAL_PROFILES.items():
        for country, profile in by_country.items():
            records.append(_draw_row(rng, name, country, profile))
        used_names.add(name)

    # --- preenchimento sintético
    remaining = max(0, rows - len(records))
    per_country = remaining // len(COUNTRIES)
    for country in COUNTRIES:
        made = 0
        while made < per_country:
            name = _make_name(rng, country, used_names)
            profile = str(rng.choice(profile_names, p=profile_p))
            records.append(_draw_row(rng, name, country, profile))
            made += 1
            # ~18% dos artistas circulam por mais de uma praça — é o que dá
            # conteúdo para a leitura de rota de turnê na ficha
            if rng.random() < 0.18 and made < per_country:
                others = [c for c in COUNTRIES if c != country]
                for other in rng.choice(others, size=int(rng.integers(1, 3)), replace=False):
                    other_profile = str(rng.choice(profile_names, p=profile_p))
                    records.append(_draw_row(rng, name, str(other), other_profile))

    df = pd.DataFrame.from_records(records)
    df = df.drop_duplicates(subset=["artist_uri", "country"], keep="first").reset_index(drop=True)

    # country_stream_share: fatia da praça no total do artista nas 5 praças
    artist_total = df.groupby("artist_uri")["total_streams"].transform("sum")
    df["country_stream_share"] = (df["total_streams"] / artist_total).clip(0, 1)

    # recommend_label: a regra do notebook 02, seção 1
    streams_pct = df.groupby("country")["total_streams"].rank(pct=True)
    df["recommend_label"] = np.where(
        (df["days_since_last_seen"] <= 90) & (streams_pct >= 0.90), "high",
        np.where(df["days_since_last_seen"] > 180, "low", "medium"),
    )

    df["total_tracks"] = df["total_tracks"].astype("int64")
    df["entry_count"] = df["entry_count"].astype("int64")
    df["days_since_last_seen"] = df["days_since_last_seen"].astype("int64")
    df["merged_uris_count"] = df["merged_uris_count"].astype("int64")
    df["cluster"] = df["cluster"].astype("int64")

    return df[list(REQUIRED_COLUMNS)]


def build_meta(df: pd.DataFrame) -> dict:
    return {
        "dataset_version": "seed-0.1",
        "is_fixture": True,
        "fixture_notice": (
            "Dados de demonstração. Âncoras reais extraídas das saídas dos "
            "notebooks (top BR e artistas internacionais); o restante é "
            "sintético, gerado a partir dos centroides de cluster e das "
            "proporções medidas. Não apresente estes números como resultado."
        ),
        "reference_date": REFERENCE_DATE.isoformat(),
        "window_start": WINDOW_START.isoformat(),
        "window_end": REFERENCE_DATE.isoformat(),
        "countries": list(COUNTRIES),
        "row_count": int(len(df)),
        "artist_count": int(df["artist_uri"].nunique()),
        # métricas reais do notebook 02, conjunto de teste
        "model_metrics": {
            "rf_f1_macro_test": 0.6110,
            "rf_f1_weighted_test": 0.7187,
            "rf_cv_f1_macro": 0.6027,
            "xgb_f1_macro_test": 0.6340,
            "xgb_f1_weighted_test": 0.7512,
            "high_precision_test": 0.50,
            "medium_f1_test": 0.40,
        },
        "model_used_for_score": "RandomForestClassifier (notebook 02)",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera o dataset-semente da API.")
    parser.add_argument("--out", default="data/api", help="diretório de saída")
    parser.add_argument("--rows", type=int, default=600, help="linhas artista x praça alvo")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    df = build_seed(rows=args.rows, random_state=args.seed)
    validate_or_raise(df, source="dataset-semente")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out / "artists.parquet", index=False)
    meta = build_meta(df)
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"OK  {len(df)} linhas / {df['artist_uri'].nunique()} artistas -> {out / 'artists.parquet'}")
    print(f"    perfis: {df['profile'].value_counts().to_dict()}")
    print(f"    alvo  : {df['recommend_label'].value_counts(normalize=True).round(3).to_dict()}")
    print(f"    momento: {df['trend_status'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()
