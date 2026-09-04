"""Pipeline completo, dos CSVs brutos ao dataset servido pela API.

Porta os notebooks 00 -> 03 -> 02 para um script executável (essa é a ordem
real de dependência: o 02 consome os clusters do 03). Diferente dos
notebooks, este script **persiste os modelos** e escreve `data/api/` com o
contrato que a API valida no boot.

Roda a base inteira: 42,9 M de linhas em 73 praças. A leitura é streaming
(uma passada, Parquet particionado por praça em disco), e o agregado roda
uma praça de cada vez — o pico de memória fica no tamanho de UMA praça.

Uso normal:

    python -m src.pipeline.build_dataset --charts charts_songs_daily.csv

`--artists artists.csv` é opcional: sem ele as três features de ouvintes
mensais ficam nulas e o modelo roda só com as features de chart.

Testar rápido em poucas praças:

    python -m src.pipeline.build_dataset --countries br pt --keep-staging

Caminho curto, se alguém do time ainda tem `data/processed/`:

    python -m src.pipeline.build_dataset --from-processed

Dependências: além do que a API usa, precisa de scikit-learn. Ver
`requirements-pipeline.txt`.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "api"))

from app.contract import GLOBAL_MARKET, REQUIRED_COLUMNS  # noqa: E402
from app.validation import validate_or_raise  # noqa: E402

CLUSTER_RAW_FEATURES = ["total_tracks", "total_streams", "days_on_chart_total",
                        "stream_concentration", "entry_count"]

BEST_K = 5


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


# ==========================================================================
# 00 — carga e engenharia de atributos
# ==========================================================================


def stage_by_market(charts_csv: Path, staging: Path, only: list[str] | None = None) -> tuple[pd.Timestamp, list[str]]:
    """Uma passada pelo CSV, gravando Parquet particionado por praça.

    A base completa tem 42,9 M de linhas em 73 praças. O notebook fazia
    `.compute()` num pandas só, o que funcionava para 5 países (3,4 M de
    linhas) e estoura a memória para a base inteira. Aqui a leitura é
    streaming: cada praça vira uma partição em disco, e o agregado roda
    uma praça de cada vez — o pico de memória fica no tamanho de UMA
    praça (~687 mil linhas), não da base.

    Devolve (data de corte global, praças encontradas).
    """
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.csv as pv
    import pyarrow.dataset as pds

    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    column_types = {
        "date": pa.string(), "country": pa.string(), "rank": pa.int32(),
        "uri": pa.string(), "streams": pa.float64(), "days_on_chart": pa.float64(),
        "entry_status": pa.string(), "label": pa.string(),
        "artist_uris": pa.string(), "artist_names": pa.string(),
    }

    reader = pv.open_csv(
        charts_csv,
        read_options=pv.ReadOptions(block_size=64 << 20),
        convert_options=pv.ConvertOptions(
            include_columns=list(column_types), column_types=column_types
        ),
    )

    seen: set[str] = set()
    max_date = ""
    total = 0

    def batches():
        nonlocal max_date, total
        for batch in reader:
            total += batch.num_rows
            seen.update(batch.column("country").unique().to_pylist())
            batch_max = pc.max(batch.column("date")).as_py()
            if batch_max and batch_max > max_date:
                max_date = batch_max
            if only is not None:
                mask = pc.is_in(batch.column("country"), value_set=pa.array(only))
                batch = batch.filter(mask)
                if batch.num_rows == 0:
                    continue
            yield batch
            if total % 10_000_000 < batch.num_rows:
                log(f"  ...{total:,} linhas lidas")

    log(f"Passada única em {charts_csv} -> {staging}")
    pds.write_dataset(
        pa.RecordBatchReader.from_batches(reader.schema, batches()),
        staging,
        format="parquet",
        partitioning=pds.partitioning(pa.schema([("country", pa.string())]), flavor="hive"),
        existing_data_behavior="overwrite_or_ignore",
        max_rows_per_group=500_000,
    )

    markets = sorted(seen if only is None else (seen & set(only)))
    log(f"{total:,} linhas em {len(markets)} praças. Data de corte: {max_date}")
    return pd.Timestamp(max_date), markets


def _align_names(df: pd.DataFrame, country: str) -> pd.Series:
    """Alinha `artist_names` com `artist_uris`, elemento a elemento.

    As duas colunas são listas separadas por `|`, mas o nome do artista
    pode conter o próprio separador — existe um "COPY RIGHT | MUSIC" na
    base — e aí as listas saem com tamanhos diferentes e o explode duplo
    quebra. A lista de URIs é a autoridade sobre quantos artistas existem
    na faixa, porque URI nunca contém `|`.

    Quando os tamanhos batem, o par é posicional. Quando não batem e há
    uma única URI, o nome inteiro é daquele artista (é exatamente o caso do
    separador dentro do nome). Nos demais não dá para saber a quem cada
    pedaço pertence, então preenchemos o que dá e deixamos o resto nulo —
    o lookup de nomes recupera pelas outras faixas do mesmo artista.
    """
    uris = df["artist_uris"].fillna("").str.split("|")
    names = df["artist_names"].fillna("").str.split("|")
    mismatch = uris.str.len() != names.str.len()

    n_bad = int(mismatch.sum())
    if n_bad:
        raw = df["artist_names"].fillna("")
        fixed = []
        for idx in names.index[mismatch]:
            u_list, n_list = uris.at[idx], names.at[idx]
            if len(u_list) == 1:
                fixed.append([raw.at[idx]])
            elif len(n_list) > len(u_list):
                fixed.append(n_list[: len(u_list)])
            else:
                fixed.append(n_list + [None] * (len(u_list) - len(n_list)))
        names = names.copy()
        names.loc[mismatch] = pd.Series(fixed, index=names.index[mismatch], dtype=object)
        log(f"    {country}: {n_bad} linha(s) com nome contendo o separador — realinhadas")

    return names


def aggregate_market(staging: Path, country: str, ref_date: pd.Timestamp) -> pd.DataFrame:
    """Engenharia de atributos de UMA praça (notebook 00, seções 3 e 4)."""
    part = staging / f"country={country}"
    df = pd.read_parquet(part)
    df["country"] = country
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    # colaborações: uma linha por artista participante
    df["artist_uri_list"] = df["artist_uris"].fillna("").str.split("|")
    df["artist_name_list"] = _align_names(df, country)
    df_exp = df.explode(["artist_uri_list", "artist_name_list"]).rename(
        columns={"artist_uri_list": "artist_uri", "artist_name_list": "artist_name_solo"}
    )
    df_exp["artist_uri"] = df_exp["artist_uri"].str.strip()
    df_exp["artist_name_solo"] = df_exp["artist_name_solo"].str.strip()
    df_exp = df_exp[df_exp["artist_uri"].notna() & (df_exp["artist_uri"] != "")]

    # O nome vem de um lookup, não de `first` no groupby: assim uma linha
    # sem nome não sequestra a identidade do artista quando ele aparece
    # nomeado em outra faixa.
    named = df_exp[df_exp["artist_name_solo"].notna() & (df_exp["artist_name_solo"] != "")]
    name_map = named.drop_duplicates("artist_uri").set_index("artist_uri")["artist_name_solo"]

    features = df_exp.groupby(["artist_uri", "country"]).agg(
        total_tracks=("uri", "nunique"),
        total_streams=("streams", "sum"),
        avg_rank=("rank", "mean"),
        best_rank=("rank", "min"),
        days_on_chart_total=("days_on_chart", "max"),
        first_entry_date=("date", "min"),
        last_seen_date=("date", "max"),
        entry_count=("entry_status", lambda x: (x == "NEW_ENTRY").sum()),
        label_mode=("label", lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else "Unknown"),
    ).reset_index()
    features["artist_name"] = features["artist_uri"].map(name_map)

    # concentração: fatia da faixa mais tocada no total do artista
    ts = df_exp.groupby(["artist_uri", "country", "uri"])["streams"].sum().reset_index()
    top_t = ts.sort_values("streams", ascending=False).groupby(["artist_uri", "country"]).first().reset_index()
    tot = ts.groupby(["artist_uri", "country"])["streams"].sum().reset_index(name="tot_s")
    conc = top_t.merge(tot, on=["artist_uri", "country"])
    conc["stream_concentration"] = np.where(conc["tot_s"] > 0, conc["streams"] / conc["tot_s"], np.nan)
    features = features.merge(
        conc[["artist_uri", "country", "stream_concentration"]], on=["artist_uri", "country"], how="left"
    )

    # tendências contra a janela imediatamente anterior, sempre relativas à
    # data de corte GLOBAL — senão uma praça que parou de reportar antes
    # pareceria em declínio só por causa do próprio calendário
    for days, col in ((30, "trend_30d"), (90, "trend_90d")):
        cut = ref_date - pd.Timedelta(days=days)
        recent = df_exp[df_exp["date"] >= cut].groupby(["artist_uri", "country"])["streams"].sum().reset_index(name="s_r")
        older = (
            df_exp[(df_exp["date"] >= cut - pd.Timedelta(days=days)) & (df_exp["date"] < cut)]
            .groupby(["artist_uri", "country"])["streams"].sum().reset_index(name="s_o")
        )
        t = recent.merge(older, on=["artist_uri", "country"], how="outer").fillna(0)
        t[col] = np.where(t["s_o"] > 0, (t["s_r"] - t["s_o"]) / t["s_o"], np.where(t["s_r"] > 0, 1.0, 0.0))
        features = features.merge(t[["artist_uri", "country", col]], on=["artist_uri", "country"], how="left")

    features["days_since_last_seen"] = (ref_date - features["last_seen_date"]).dt.days
    return features


def fill_missing_names(features: pd.DataFrame) -> pd.DataFrame:
    """Recupera nomes entre praças.

    O lookup de nomes de `aggregate_market` só enxerga uma praça. Se um
    artista nunca aparece nomeado ali — porque entrou só em colaborações
    com o campo de nomes vazio naquela posição — a linha sai sem nome
    mesmo o nome existindo em outro mercado. O nome do artista não depende
    da praça, então aqui completamos com o que qualquer outra já resolveu.
    """
    missing = features["artist_name"].isna() | (features["artist_name"].fillna("").str.strip() == "")
    if not missing.any():
        return features

    known = features.loc[~missing].drop_duplicates("artist_uri").set_index("artist_uri")["artist_name"]
    recovered = features.loc[missing, "artist_uri"].map(known)
    features.loc[missing, "artist_name"] = recovered

    n_ok = int(recovered.notna().sum())
    n_left = int(missing.sum()) - n_ok
    log(f"Nomes recuperados de outras praças: {n_ok}; ainda sem nome: {n_left}")
    return features


def attach_listeners(features: pd.DataFrame, artists_csv: Path | None) -> pd.DataFrame:
    """Junta ouvintes mensais do artists.csv, se ele existir.

    O arquivo é opcional: sem ele o produto continua de pé, só perde três
    features (que já vinham com 25% de nulos e são GLOBAIS, não por praça).
    """
    if artists_csv is None or not artists_csv.exists():
        log("AVISO: artists.csv ausente — monthly_listeners/peak_listeners/listener_ratio ficam nulos.")
        features["monthly_listeners"] = np.nan
        features["peak_listeners"] = np.nan
        features["listener_ratio"] = np.nan
        return features

    log(f"Lendo {artists_csv}")
    df_artists = pd.read_csv(artists_csv)
    ai = df_artists[["artist_uri", "monthly_listeners", "monthly_listeners_peak_listeners"]].copy()
    ai.columns = ["artist_uri", "monthly_listeners", "peak_listeners"]
    ai = ai.drop_duplicates(subset=["artist_uri"])
    features = features.merge(ai, on="artist_uri", how="left")
    features["listener_ratio"] = np.where(
        features["peak_listeners"] > 0, features["monthly_listeners"] / features["peak_listeners"], np.nan
    )
    cobertura = features["monthly_listeners"].notna().mean()
    log(f"Ouvintes mensais preenchidos em {cobertura:.1%} das linhas")
    return features


def load_features(
    charts_csv: Path,
    artists_csv: Path | None,
    staging: Path,
    only: list[str] | None = None,
) -> pd.DataFrame:
    ref_date, markets = stage_by_market(charts_csv, staging, only)

    frames = []
    for i, country in enumerate(markets, 1):
        frame = aggregate_market(staging, country, ref_date)
        frames.append(frame)
        log(f"  [{i}/{len(markets)}] {country}: {len(frame):,} artistas")

    features = pd.concat(frames, ignore_index=True)
    log(f"Total antes da consolidação: {len(features):,} linhas artista x praça")
    features = fill_missing_names(features)
    features = attach_listeners(features, artists_csv)
    return consolidate_duplicate_profiles(features)


def consolidate_duplicate_profiles(features: pd.DataFrame) -> pd.DataFrame:
    """Notebook 00, seção 5.1.

    O mesmo artista às vezes tem mais de um `artist_uri` no Spotify (perfil
    legado). Sem consolidar, o sinal fica partido entre os perfis e um
    artista grande aparece pequeno.
    """
    valid_name = features["artist_name"].notna() & (features["artist_name"].str.strip() != "")
    dup_key = features.loc[valid_name].groupby(["artist_name", "country"])["artist_uri"].transform("nunique")

    singles = features[~valid_name | (valid_name & (dup_key == 1))].copy()
    dupes = features[valid_name & (dup_key > 1)].copy()
    log(f"Consolidando {dupes.groupby(['artist_name', 'country']).ngroups} grupos de perfis duplicados")

    rows = []
    for (name, country), g in dupes.groupby(["artist_name", "country"]):
        g = g.sort_values("total_streams", ascending=False)
        dominant = g.iloc[0]
        total_streams = g["total_streams"].sum()
        weights = g["days_on_chart_total"].clip(lower=1)
        monthly = g["monthly_listeners"].dropna()
        peak = g["peak_listeners"].dropna()
        rows.append({
            "artist_uri": dominant["artist_uri"], "country": country, "artist_name": name,
            "total_tracks": g["total_tracks"].sum(), "total_streams": total_streams,
            "avg_rank": (g["avg_rank"] * weights).sum() / weights.sum(),
            "best_rank": g["best_rank"].min(),
            "days_on_chart_total": g["days_on_chart_total"].max(),
            "first_entry_date": g["first_entry_date"].min(),
            "last_seen_date": g["last_seen_date"].max(),
            "entry_count": g["entry_count"].sum(), "label_mode": dominant["label_mode"],
            "stream_concentration": (
                (g["stream_concentration"] * g["total_streams"]).sum() / total_streams
                if total_streams > 0 else g["stream_concentration"].mean()
            ),
            "trend_30d": dominant["trend_30d"], "trend_90d": dominant["trend_90d"],
            "monthly_listeners": monthly.max() if len(monthly) else np.nan,
            "peak_listeners": peak.max() if len(peak) else np.nan,
            "merged_uris_count": len(g),
        })

    consolidated = pd.DataFrame(rows).reset_index(drop=True)
    if not consolidated.empty:
        consolidated["listener_ratio"] = np.where(
            consolidated["peak_listeners"] > 0,
            consolidated["monthly_listeners"] / consolidated["peak_listeners"], np.nan,
        )
    singles["merged_uris_count"] = 1

    out = pd.concat([singles, consolidated], ignore_index=True, sort=False)
    ref_date = out["last_seen_date"].max()
    out["days_since_last_seen"] = (ref_date - out["last_seen_date"]).dt.days
    out["merged_uris_count"] = out["merged_uris_count"].fillna(1).astype(int)
    log(f"Features finais: {out.shape}")
    return out


# ==========================================================================
# 03 — perfis de carreira
# ==========================================================================


def build_clusters(features: pd.DataFrame, models_dir: Path) -> pd.DataFrame:
    import joblib
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler

    # Só forma estrutural de carreira. Tendência/recência/rank ficam fora:
    # são a base da regra de recommend_label no 02, e realimentá-las aqui
    # reintroduziria o vazamento que já foi removido lá.
    X = features[CLUSTER_RAW_FEATURES].copy()
    X["log_total_streams"] = np.log1p(X["total_streams"])
    X["log_total_tracks"] = np.log1p(X["total_tracks"])
    X = X.drop(columns=["total_streams", "total_tracks"])

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    km = KMeans(n_clusters=BEST_K, random_state=42, n_init=20, max_iter=500)
    labels = km.fit_predict(X_scaled)
    out = features.copy()
    out["cluster"] = labels

    profiles = out.groupby("cluster")[CLUSTER_RAW_FEATURES].mean()
    profiles = profiles.join(
        X[["log_total_streams", "log_total_tracks"]].groupby(out["cluster"]).mean()
    )

    # Nomes por característica do centroide, nunca por ID: o cluster_id do
    # KMeans muda entre execuções, e um mapa fixo já rotulou veterano como
    # efêmero uma vez.
    scale_cols = ["log_total_streams", "log_total_tracks", "days_on_chart_total", "entry_count"]
    z = (profiles[scale_cols] - profiles[scale_cols].mean()) / profiles[scale_cols].std()
    profiles["scale_score"] = z.mean(axis=1)

    concentrated = profiles["stream_concentration"] >= 0.8
    diversified = profiles[~concentrated].sort_values("scale_score", ascending=False)
    concentrated_p = profiles[concentrated].sort_values("scale_score", ascending=False)

    names: dict[int, str] = {}
    names.update(dict(zip(diversified.index,
                          ["Veterano Consistente", "Consolidado", "Nicho Recorrente"])))
    names.update(dict(zip(concentrated_p.index, ["One-Hit Wonder", "Efemero Cauda Longa"])))
    log(f"Mapa cluster -> perfil desta execução: {names}")

    out["profile"] = out["cluster"].map(names)
    if out["profile"].isna().any():
        raise RuntimeError(
            "Algum cluster ficou sem nome — a separação por concentração não "
            f"produziu 3 diversificados e 2 concentrados. Centroides:\n{profiles}"
        )

    def trend_status(row: pd.Series) -> str:
        recent = row["days_since_last_seen"] <= 90
        t90 = row["trend_90d"]
        if recent and pd.notna(t90) and t90 > 0.2:
            return "Em Ascensao"
        if recent and pd.notna(t90) and t90 < -0.2:
            return "Em Declinio"
        if recent:
            return "Estavel"
        if row["days_since_last_seen"] <= 365 and pd.notna(t90) and t90 > 0:
            return "Possivel Retomada"
        return "Inativo"

    out["trend_status"] = out.apply(trend_status, axis=1)

    models_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump({"scaler": scaler, "kmeans": km, "cluster_names": names,
                 "features": list(X.columns)}, models_dir / "clustering.joblib")
    log(f"Modelo de clustering salvo em {models_dir / 'clustering.joblib'}")
    return out


# ==========================================================================
# 02 — score de recomendação
# ==========================================================================


def build_scores(df: pd.DataFrame, models_dir: Path) -> tuple[pd.DataFrame, dict[str, float]]:
    import joblib
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.metrics import f1_score, precision_score
    from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import LabelEncoder

    df = df.copy()

    # Percentil de streams dentro do país, não avg_rank absoluto: avg_rank
    # penaliza catálogo grande, e os artistas que de fato dominam o mercado
    # ficavam de fora do corte.
    df["streams_pct"] = df.groupby("country")["total_streams"].rank(pct=True)
    df["recommend_label"] = np.where(
        (df["days_since_last_seen"] <= 90) & (df["streams_pct"] >= 0.90), "high",
        np.where(df["days_since_last_seen"] > 180, "low", "medium"),
    )
    log(f"Distribuição do alvo: {df['recommend_label'].value_counts().to_dict()}")

    # Sinal genuinamente por praça — monthly_listeners é global e se repete
    # igual em todos os países do artista.
    #
    # O chart 'global' fica FORA do denominador: ele já é o agregado de todas
    # as praças, então incluí-lo contaria cada stream duas vezes e cortaria a
    # fatia real de cada país pela metade.
    real_markets = df["country"] != GLOBAL_MARKET
    market_total = (
        df.where(real_markets).groupby(df["artist_uri"])["total_streams"].transform("sum")
    )
    df["country_stream_share"] = np.where(
        market_total > 0, (df["total_streams"] / market_total).clip(0, 1), np.nan
    )
    # a linha 'global' representa o artista inteiro, por definição
    df.loc[~real_markets, "country_stream_share"] = 1.0
    df["country_stream_share"] = df["country_stream_share"].fillna(1.0)

    profile_dummies = pd.get_dummies(df["profile"].str.replace(" ", "_"), prefix="profile")
    df = pd.concat([df, profile_dummies], axis=1)

    # Colunas de ouvintes só entram se o artists.csv estiver presente; se
    # vierem 100% nulas, um imputador de mediana não tem o que imputar.
    impute_cols = [c for c in ("monthly_listeners", "peak_listeners", "listener_ratio")
                   if df[c].notna().any()]
    if not impute_cols:
        log("Sem dados de ouvintes — o modelo roda só com as features de chart.")
    passthrough_cols = ["total_tracks", "total_streams", "days_on_chart_total",
                        "stream_concentration", "entry_count", "country_stream_share"]
    feature_cols = impute_cols + passthrough_cols + profile_dummies.columns.tolist()

    X = df[feature_cols]
    le = LabelEncoder()
    y = le.fit_transform(df["recommend_label"])

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    transformers = (
        [("impute", SimpleImputer(strategy="median", add_indicator=True), impute_cols)]
        if impute_cols else []
    )
    pipe = Pipeline([
        ("prep", ColumnTransformer(transformers, remainder="passthrough")),
        ("clf", RandomForestClassifier(
            n_estimators=200, max_depth=6, min_samples_leaf=20, min_samples_split=40,
            max_features="sqrt", class_weight="balanced", random_state=42, n_jobs=-1,
        )),
    ])
    pipe.fit(X_train, y_train)

    y_pred = pipe.predict(X_test)
    classes = list(le.classes_)
    high_idx = classes.index("high")
    medium_idx = classes.index("medium")
    cv = cross_val_score(
        pipe, X_train, y_train,
        cv=StratifiedKFold(n_splits=5, shuffle=True, random_state=42),
        scoring="f1_macro", n_jobs=-1,
    )

    metrics = {
        "rf_f1_macro_test": float(f1_score(y_test, y_pred, average="macro")),
        "rf_f1_weighted_test": float(f1_score(y_test, y_pred, average="weighted")),
        "rf_f1_macro_train": float(f1_score(y_train, pipe.predict(X_train), average="macro")),
        "rf_cv_f1_macro": float(cv.mean()),
        "high_precision_test": float(
            precision_score(y_test, y_pred, labels=[high_idx], average="micro", zero_division=0)
        ),
        "medium_f1_test": float(
            f1_score(y_test, y_pred, labels=[medium_idx], average="micro", zero_division=0)
        ),
    }
    log("Métricas: " + ", ".join(f"{k}={v:.4f}" for k, v in metrics.items()))
    if metrics["rf_f1_macro_train"] - metrics["rf_f1_macro_test"] > 0.15:
        log("AVISO: diferença grande entre treino e teste — checar overfit antes de publicar.")

    df["recommend_score"] = pipe.predict_proba(X)[:, high_idx] * 100

    models_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump({"pipeline": pipe, "label_encoder": le, "feature_cols": feature_cols,
                 "metrics": metrics}, models_dir / "recommender.joblib")
    log(f"Modelo supervisionado salvo em {models_dir / 'recommender.joblib'}")
    return df, metrics


# ==========================================================================
# export
# ==========================================================================


def export(df: pd.DataFrame, metrics: dict[str, float], out_dir: Path, version: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise RuntimeError(f"Pipeline não produziu as colunas: {missing}")

    final = df[list(REQUIRED_COLUMNS)].copy()

    # Artistas que nunca aparecem nomeados em nenhuma faixa da praça. Só
    # marcamos aqui, no fim: até a consolidação eles precisam continuar
    # nulos, senão o placeholder viraria chave de agrupamento e juntaria
    # artistas diferentes numa linha só.
    sem_nome = final["artist_name"].isna() | (final["artist_name"].fillna("").str.strip() == "")
    if sem_nome.any():
        log(f"AVISO: {int(sem_nome.sum())} linha(s) sem nome de artista — exportadas como '(sem nome)'")
        final.loc[sem_nome, "artist_name"] = "(sem nome)"

    validate_or_raise(final, source="dataset do pipeline")

    final.to_parquet(out_dir / "artists.parquet", index=False)

    ref_date = pd.to_datetime(final["last_seen_date"]).max()
    meta = {
        "dataset_version": version,
        "is_fixture": False,
        "fixture_notice": None,
        "reference_date": ref_date.date().isoformat(),
        "window_start": pd.to_datetime(final["first_entry_date"]).min().date().isoformat(),
        "window_end": ref_date.date().isoformat(),
        "countries": sorted(final["country"].unique().tolist()),
        "row_count": int(len(final)),
        "artist_count": int(final["artist_uri"].nunique()),
        "model_metrics": metrics,
        "model_used_for_score": "RandomForestClassifier (notebook 02)",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Dataset da API escrito em {out_dir}")


def sanity_checks(
    df: pd.DataFrame,
    expected_markets: int | None = None,
    min_rows: int = 10_000,
) -> None:
    """Checagens do plano — falham alto, antes de qualquer coisa ir para a tela."""
    problems = []
    countries = set(df["country"].unique())

    if len(df) < min_rows:
        problems.append(f"só {len(df)} linhas; esperava pelo menos {min_rows:,}")
    if expected_markets is not None and len(countries) != expected_markets:
        problems.append(
            f"esperava {expected_markets} praças, vieram {len(countries)}: {sorted(countries)}"
        )

    # Um punhado de nomes ausentes é dado da fonte; muitos indicam que a
    # explosão de colaborações desalinhou. Só o segundo caso derruba a
    # rodada — o primeiro vira aviso.
    limite_nomes_vazios = 5
    for country in sorted(countries):
        top = df[df["country"] == country].nlargest(200, "total_streams")
        nome = top["artist_name"].fillna("").str.strip()
        vazios = int((nome == "").sum())
        if vazios > limite_nomes_vazios:
            problems.append(
                f"{country}: {vazios} nomes vazios no top 200 de streams "
                f"(acima do limite de {limite_nomes_vazios} — suspeita de desalinhamento)"
            )
        elif vazios:
            log(f"AVISO: {country} tem {vazios} nome(s) vazio(s) no top 200 — dado ausente na fonte")

    if "br" in countries:
        top_br = set(df[df["country"] == "br"].nlargest(10, "total_streams")["artist_name"])
        esperados = {"Henrique & Juliano", "Marília Mendonça", "Gusttavo Lima"}
        if not (esperados & top_br):
            problems.append(
                f"top BR por streams não traz nenhum dos nomes esperados {esperados}: {sorted(top_br)}"
            )

    if problems:
        raise RuntimeError("Checagens de sanidade falharam:\n" + "\n".join(f"  - {p}" for p in problems))
    log(f"Checagens de sanidade OK ({len(countries)} praças, {len(df):,} linhas)")


def report_tiers(df: pd.DataFrame) -> None:
    """Os cortes de faixa foram chutados no plano. Aqui dá para calibrar."""
    from app.labels import tier_for

    tiers = df["recommend_score"].map(tier_for).value_counts()
    log("Distribuição de faixas com os cortes atuais (85 / 60 / 30):")
    for name in ("forte", "boa", "risco", "sem_lastro"):
        n = int(tiers.get(name, 0))
        log(f"    {name:<11} {n:>6}  ({n / len(df):.1%})")
    q = df["recommend_score"].quantile([0.5, 0.75, 0.9, 0.95, 0.99]).round(1)
    log(f"    percentis do score: {q.to_dict()}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--charts", type=Path, default=Path("charts_songs_daily.csv"))
    parser.add_argument("--artists", type=Path, default=Path("artists.csv"),
                        help="opcional: sem ele, as features de ouvintes ficam nulas")
    parser.add_argument("--processed", type=Path, default=Path("data/processed"))
    parser.add_argument("--from-processed", action="store_true",
                        help="pula a etapa pesada e usa data/processed/artist_country_features.parquet")
    parser.add_argument("--countries", nargs="*", default=None,
                        help="restringe a estas praças (padrão: todas as 73 da base)")
    parser.add_argument(
        "--staging", type=Path,
        default=Path(tempfile.gettempdir()) / "spotify-analyzer-staging",
        help="onde gravar o Parquet particionado da passada única; fora do "
             "repositório por padrão, para não jogar GBs no OneDrive",
    )
    parser.add_argument("--keep-staging", action="store_true",
                        help="não apaga o staging no fim (útil para reprocessar rápido)")
    parser.add_argument("--out", type=Path, default=Path("data/api"))
    parser.add_argument("--models", type=Path, default=Path("models"))
    parser.add_argument("--version", default=datetime.now().strftime("charts-%Y%m%d"))
    args = parser.parse_args()

    cached = args.processed / "artist_country_features.parquet"
    if args.from_processed:
        if not cached.exists():
            raise SystemExit(
                f"{cached} não existe. Rode sem --from-processed (precisa dos CSVs brutos) "
                "ou peça a alguém do time o data/processed/."
            )
        log(f"Usando features já processadas de {cached}")
        features = fill_missing_names(pd.read_parquet(cached))
    else:
        if not args.charts.exists():
            raise SystemExit(f"{args.charts} não encontrado. Veja --help para o caminho curto.")
        features = load_features(args.charts, args.artists, args.staging, args.countries)
        args.processed.mkdir(parents=True, exist_ok=True)
        features.to_parquet(cached, index=False)
        log(f"Features intermediárias salvas em {cached}")
        if not args.keep_staging:
            shutil.rmtree(args.staging, ignore_errors=True)

    with_clusters = build_clusters(features, args.models)
    with_clusters[["artist_uri", "artist_name", "country", "cluster", "profile", "trend_status"]].to_csv(
        args.processed / "cluster_labels.csv", index=False
    )

    scored, metrics = build_scores(with_clusters, args.models)
    scored[["artist_uri", "artist_name", "country", "profile", "trend_status",
            "recommend_label", "recommend_score"]].to_csv(
        args.processed / "model_results.csv", index=False
    )

    # Numa rodada restrita a poucas praças o piso de linhas não se aplica.
    sanity_checks(
        scored,
        expected_markets=features["country"].nunique(),
        min_rows=10_000 if not args.countries else 100,
    )
    report_tiers(scored)
    export(scored, metrics, args.out, args.version)

    log("Pronto. Suba a API com:  uvicorn app.main:app --app-dir api")


if __name__ == "__main__":
    main()
