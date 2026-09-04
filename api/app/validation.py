"""Validação do dataset contra o contrato.

Roda no startup da API. Se o Parquet real divergir do que os notebooks
produziam, queremos saber aqui — não numa tabela em branco no front.
"""

from __future__ import annotations

import pandas as pd

from .contract import COLUMNS_BY_NAME, DERIVED, GLOBAL_MARKET, REQUIRED_COLUMNS, Column


class DatasetContractError(Exception):
    """Dataset não cumpre o contrato. A mensagem lista tudo que divergiu."""


def _check_kind(series: pd.Series, col: Column) -> str | None:
    if col.kind == "str":
        if not (pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series)):
            return f"esperava texto, veio {series.dtype}"
    elif col.kind == "int":
        if not (pd.api.types.is_integer_dtype(series) or pd.api.types.is_float_dtype(series)):
            return f"esperava número inteiro, veio {series.dtype}"
    elif col.kind == "float":
        if not pd.api.types.is_numeric_dtype(series):
            return f"esperava número, veio {series.dtype}"
    elif col.kind == "bool":
        if not pd.api.types.is_bool_dtype(series):
            return f"esperava booleano, veio {series.dtype}"
    elif col.kind == "date":
        if not pd.api.types.is_datetime64_any_dtype(series):
            return f"esperava data, veio {series.dtype}"
    return None


def validate(df: pd.DataFrame, *, strict_ranges: bool = True) -> list[str]:
    """Devolve a lista de problemas encontrados. Lista vazia = dataset válido."""
    problems: list[str] = []

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        problems.append(f"colunas ausentes: {', '.join(missing)}")

    if df.empty:
        problems.append("dataset vazio")
        return problems

    for name in df.columns:
        col = COLUMNS_BY_NAME.get(name)
        if col is None:
            continue  # colunas extras são toleradas
        series = df[name]

        kind_problem = _check_kind(series, col)
        if kind_problem:
            problems.append(f"{name}: {kind_problem}")
            continue

        if not col.nullable:
            n_null = int(series.isna().sum())
            if n_null:
                problems.append(f"{name}: {n_null} valores nulos, coluna não aceita nulo")

        if col.domain is not None:
            extra = set(series.dropna().unique()) - set(col.domain)
            if extra:
                shown = ", ".join(sorted(map(str, extra))[:5])
                problems.append(f"{name}: valores fora do domínio ({shown})")

        if strict_ranges and col.kind in {"int", "float"}:
            valid = series.dropna()
            if col.minimum is not None and len(valid) and float(valid.min()) < col.minimum:
                problems.append(f"{name}: mínimo {valid.min():.4g} abaixo do permitido ({col.minimum})")
            if col.maximum is not None and len(valid) and float(valid.max()) > col.maximum:
                problems.append(f"{name}: máximo {valid.max():.4g} acima do permitido ({col.maximum})")

    if "country" in df.columns and pd.api.types.is_string_dtype(df["country"]):
        codes = set(df["country"].dropna().unique())
        invalid = {c for c in codes if c != GLOBAL_MARKET and not (len(c) == 2 and c.isalpha())}
        if invalid:
            shown = ", ".join(sorted(invalid)[:5])
            problems.append(f"country: códigos que não são ISO de 2 letras nem 'global' ({shown})")
        if any(c != c.lower() for c in codes):
            problems.append("country: códigos precisam estar em caixa baixa")

    if {"artist_uri", "country"} <= set(df.columns):
        dupes = int(df.duplicated(subset=["artist_uri", "country"]).sum())
        if dupes:
            problems.append(f"{dupes} linhas duplicadas em (artist_uri, country)")

    if {"first_entry_date", "last_seen_date"} <= set(df.columns):
        try:
            invertidas = int((df["last_seen_date"] < df["first_entry_date"]).sum())
            if invertidas:
                problems.append(f"{invertidas} linhas com last_seen_date anterior a first_entry_date")
        except TypeError:
            pass  # tipo já reportado acima

    return problems


def validate_or_raise(df: pd.DataFrame, *, source: str = "dataset", strict_ranges: bool = True) -> None:
    problems = validate(df, strict_ranges=strict_ranges)
    if problems:
        listed = "\n".join(f"  - {p}" for p in problems)
        raise DatasetContractError(
            f"{source} não cumpre o contrato de dados ({len(problems)} problema(s)):\n{listed}"
        )


def describe_contract() -> str:
    """Contrato em texto — útil no README e na mensagem de erro do CLI."""
    lines = ["Colunas exigidas em artists.parquet:"]
    for col in COLUMNS_BY_NAME.values():
        if col.name in DERIVED:
            continue
        flags = []
        if col.nullable:
            flags.append("nulo ok")
        if col.domain:
            flags.append("domínio fechado")
        suffix = f" [{', '.join(flags)}]" if flags else ""
        lines.append(f"  {col.name:<24} {col.kind:<6}{suffix}  {col.note}")
    return "\n".join(lines)
