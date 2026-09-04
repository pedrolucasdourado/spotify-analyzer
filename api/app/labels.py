"""Tradução de métrica em linguagem de produção de evento.

É a camada onde o MVP ganha valor: um produtor não lê
`stream_concentration = 0.96`, ele lê "depende de uma música só".
Fica no servidor, e não no front, para que o CSV exportado saia com a
mesma leitura que a tela mostra.
"""

from __future__ import annotations

import math
from typing import Any

from .contract import TIER_CUTS

# --- papel sugerido no cartaz ---------------------------------------------

ROLE_BY_PROFILE: dict[str, dict[str, str]] = {
    "Veterano Consistente": {
        "role": "Cabeça de cartaz",
        "note": "Catálogo extenso e presença longa no chart. Sustenta topo de grade.",
    },
    "Consolidado": {
        "role": "Sub-headliner",
        "note": "Base sólida, sem o volume de um veterano. Costuma ter cachê mais negociável.",
    },
    "Nicho Recorrente": {
        "role": "Meio de grade",
        "note": "Público fiel e recorrente, alcance menor. Bom para palco secundário.",
    },
    "One-Hit Wonder": {
        "role": "Atração de risco",
        "note": "O streaming vem de uma faixa só. Funciona por música, não por show.",
    },
    "Efemero Cauda Longa": {
        "role": "Sem lastro para show",
        "note": "Passagem curta pelo chart, sem volume que sustente venda de ingresso.",
    },
}

# --- faixas de aposta ------------------------------------------------------

TIER_INFO: dict[str, dict[str, Any]] = {
    "forte": {"label": "Aposta forte", "rank": 1,
              "note": "Sustenta cabeça de cartaz nesta praça."},
    "boa": {"label": "Boa aposta", "rank": 2,
            "note": "Meio de grade sólido, cachê mais negociável."},
    "risco": {"label": "Aposta de risco", "rank": 3,
              "note": "Só com um motivo além do dado."},
    "sem_lastro": {"label": "Sem lastro", "rank": 4,
                   "note": "A base não sustenta a escolha."},
}

TREND_LABEL: dict[str, str] = {
    "Em Ascensao": "Em ascensão",
    "Estavel": "Estável",
    "Em Declinio": "Em declínio",
    "Possivel Retomada": "Possível retomada",
    "Inativo": "Inativo",
}

#: Rótulo em linguagem de produção para cada coluna técnica.
METRIC_LABELS: dict[str, str] = {
    "total_streams": "Streams na janela",
    "total_tracks": "Faixas no chart",
    "entry_count": "Faixas que emplacaram",
    "days_on_chart_total": "Tempo de estrada no chart",
    "best_rank": "Melhor posição alcançada",
    "avg_rank": "Posição média",
    "stream_concentration": "Dependência de um hit",
    "country_stream_share": "Força nesta praça",
    "listener_ratio": "Está no auge ou já passou",
    "monthly_listeners": "Ouvintes mensais (global)",
    "peak_listeners": "Pico de ouvintes (global)",
    "days_since_last_seen": "Dias fora do chart",
    "label_mode": "Gravadora predominante",
    "recommend_score": "Score do modelo",
}


def tier_for(score: float) -> str:
    for name, cut in TIER_CUTS:
        if score >= cut:
            return name
    return TIER_CUTS[-1][0]


def _is_null(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def readings(row: dict[str, Any]) -> list[dict[str, str]]:
    """Leituras curtas em linguagem de produção, na ordem de importância."""
    out: list[dict[str, str]] = []

    conc = row.get("stream_concentration")
    if not _is_null(conc):
        if conc >= 0.8:
            out.append({"metric": "stream_concentration", "level": "alerta",
                        "text": f"{conc:.0%} dos streams vêm de uma faixa só — depende de um hit."})
        elif conc >= 0.5:
            out.append({"metric": "stream_concentration", "level": "atencao",
                        "text": f"{conc:.0%} do streaming concentrado na faixa principal."})
        else:
            out.append({"metric": "stream_concentration", "level": "ok",
                        "text": "Streaming distribuído pelo catálogo, não preso a um hit."})

    ratio = row.get("listener_ratio")
    if not _is_null(ratio):
        if ratio >= 0.9:
            out.append({"metric": "listener_ratio", "level": "ok",
                        "text": f"Ouvintes em {ratio:.0%} do pico histórico — está no auge."})
        elif ratio >= 0.6:
            out.append({"metric": "listener_ratio", "level": "atencao",
                        "text": f"Ouvintes em {ratio:.0%} do pico histórico."})
        else:
            out.append({"metric": "listener_ratio", "level": "alerta",
                        "text": f"Ouvintes em {ratio:.0%} do pico — o auge já passou."})

    share = row.get("country_stream_share")
    if not _is_null(share):
        if share >= 0.6:
            out.append({"metric": "country_stream_share", "level": "ok",
                        "text": f"{share:.0%} do streaming do artista vem desta praça — força local."})
        elif share <= 0.2:
            out.append({"metric": "country_stream_share", "level": "atencao",
                        "text": f"Só {share:.0%} do streaming vem desta praça — a força está em outro mercado."})

    days = row.get("days_since_last_seen")
    if not _is_null(days):
        days = int(days)
        if days == 0:
            out.append({"metric": "days_since_last_seen", "level": "ok",
                        "text": "Estava no chart no último dia da base."})
        elif days <= 90:
            out.append({"metric": "days_since_last_seen", "level": "ok",
                        "text": f"No chart há {days} dias atrás — dentro da janela ativa."})
        elif days <= 365:
            out.append({"metric": "days_since_last_seen", "level": "atencao",
                        "text": f"Fora do chart há {days} dias."})
        else:
            out.append({"metric": "days_since_last_seen", "level": "alerta",
                        "text": f"Fora do chart há {days // 365} ano(s) e {days % 365} dias."})

    chart_days = row.get("days_on_chart_total")
    if not _is_null(chart_days) and chart_days >= 365:
        anos = chart_days / 365
        out.append({"metric": "days_on_chart_total", "level": "ok",
                    "text": f"{anos:.1f} anos de presença no chart."})

    merged = row.get("merged_uris_count")
    if not _is_null(merged) and int(merged) > 1:
        out.append({"metric": "merged_uris_count", "level": "info",
                    "text": f"{int(merged)} perfis do Spotify consolidados nesta linha."})

    return out


def role_for(profile: str) -> dict[str, str]:
    return ROLE_BY_PROFILE.get(profile, {"role": "Não classificado", "note": ""})
