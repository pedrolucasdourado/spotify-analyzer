"""Contrato do dataset servido pela API.

Este módulo é a fonte única da verdade sobre o formato de
`data/api/artists.parquet`. Tanto o gerador de semente
(`src/pipeline/seed.py`) quanto o pipeline real
(`src/pipeline/build_dataset.py`) escrevem contra ele, e o carregador
da API valida contra ele no startup.

A ideia é que trocar a semente pelo Parquet real seja apenas mudar o
arquivo apontado por SPOTIFY_DATASET: se o dado real divergir do que os
notebooks produziam, a validação falha alto, no boot, em vez de quebrar
silenciosamente numa tela.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --- praças ----------------------------------------------------------------
#
# A lista de praças NÃO é um domínio fechado: ela vem do dataset carregado.
# O piloto rodava com 5 países; a base completa tem 73 praças. Só o mapa de
# nomes fica aqui, e códigos desconhecidos caem no fallback (código em caixa
# alta), em vez de derrubar a validação.

#: Chart mundial do Spotify. Não é um país: é o agregado de todas as praças.
#: Fica de fora do denominador de `country_stream_share`, senão a fatia de
#: cada país cairia pela metade por dupla contagem.
GLOBAL_MARKET = "global"

#: Praças do piloto original — usadas pelo gerador de semente e como padrão.
PILOT_COUNTRIES: tuple[str, ...] = ("br", "us", "gb", "mx", "ar")

COUNTRY_NAMES: dict[str, str] = {
    GLOBAL_MARKET: "Global (chart mundial)",
    "ae": "Emirados Árabes Unidos", "ar": "Argentina", "at": "Áustria",
    "au": "Austrália", "be": "Bélgica", "bg": "Bulgária", "bo": "Bolívia",
    "br": "Brasil", "by": "Belarus", "ca": "Canadá", "ch": "Suíça",
    "cl": "Chile", "co": "Colômbia", "cr": "Costa Rica", "cz": "Tchéquia",
    "de": "Alemanha", "dk": "Dinamarca", "do": "República Dominicana",
    "ec": "Equador", "ee": "Estônia", "eg": "Egito", "es": "Espanha",
    "fi": "Finlândia", "fr": "França", "gb": "Reino Unido", "gr": "Grécia",
    "gt": "Guatemala", "hk": "Hong Kong", "hn": "Honduras", "hu": "Hungria",
    "id": "Indonésia", "ie": "Irlanda", "il": "Israel", "in": "Índia",
    "is": "Islândia", "it": "Itália", "jp": "Japão", "kr": "Coreia do Sul",
    "kz": "Cazaquistão", "lt": "Lituânia", "lu": "Luxemburgo", "lv": "Letônia",
    "ma": "Marrocos", "mx": "México", "my": "Malásia", "ng": "Nigéria",
    "ni": "Nicarágua", "nl": "Países Baixos", "no": "Noruega",
    "nz": "Nova Zelândia", "pa": "Panamá", "pe": "Peru", "ph": "Filipinas",
    "pk": "Paquistão", "pl": "Polônia", "pt": "Portugal", "py": "Paraguai",
    "ro": "Romênia", "sa": "Arábia Saudita", "se": "Suécia", "sg": "Singapura",
    "sk": "Eslováquia", "sv": "El Salvador", "th": "Tailândia", "tr": "Turquia",
    "tw": "Taiwan", "ua": "Ucrânia", "us": "Estados Unidos", "uy": "Uruguai",
    "ve": "Venezuela", "vn": "Vietnã", "za": "África do Sul",
}


def country_name(code: str) -> str:
    return COUNTRY_NAMES.get(code, code.upper())

# Nomes atribuídos por centroide no notebook 03 (não por cluster_id, que
# muda entre execuções). Ordem = da carreira mais estruturada para a menos.
PROFILES: tuple[str, ...] = (
    "Veterano Consistente",
    "Consolidado",
    "Nicho Recorrente",
    "One-Hit Wonder",
    "Efemero Cauda Longa",
)

TREND_STATUSES: tuple[str, ...] = (
    "Em Ascensao",
    "Estavel",
    "Em Declinio",
    "Possivel Retomada",
    "Inativo",
)

RECOMMEND_LABELS: tuple[str, ...] = ("high", "medium", "low")

TIERS: tuple[str, ...] = ("forte", "boa", "risco", "sem_lastro")


# --- faixas de aposta ------------------------------------------------------
# Calibrados em 04/09/2026 contra a base completa (73 praças, 188.035 linhas).
#
# A calibração olha a população de ARTISTAS ATIVOS, não a base inteira: é o
# que o produtor vê, já que o filtro de recência vem ligado por padrão. Sobre
# a base toda qualquer corte parece brutal, porque 86% dos artistas sumiram
# do chart há mais de 90 dias.
#
# Com estes cortes, entre os ativos: 10,7% forte, 21,3% boa, 16,6% risco,
# 51,4% sem lastro — mediana de 39 "apostas fortes" por praça. Três praças
# ficam sem nenhuma (by, il, lu), e isso é honesto: têm poucas semanas de
# chart na base.
#
# `build_dataset.py` imprime a distribuição no fim de cada rodada; se a base
# mudar, recalibre aqui.
TIER_CUTS: tuple[tuple[str, float], ...] = (
    ("forte", 90.0),
    ("boa", 70.0),
    ("risco", 35.0),
    ("sem_lastro", 0.0),
)

# Um artista é considerado "ativo" se apareceu no chart nos últimos 90 dias
# em relação à data de corte da base (não em relação a hoje).
ACTIVE_MAX_DAYS_SINCE_SEEN = 90


@dataclass(frozen=True)
class Column:
    name: str
    kind: str  # "str" | "int" | "float" | "bool" | "date"
    nullable: bool = False
    domain: tuple[str, ...] | None = None
    minimum: float | None = None
    maximum: float | None = None
    note: str = ""


#: Colunas exigidas em `artists.parquet`, na ordem canônica.
#:
#: `predicted_label` do notebook 02 fica deliberadamente de fora: com F1
#: entre 0,40 e 0,43 na classe `medium`, a classe prevista não tem qualidade
#: para ir à tela. Usamos só a probabilidade (`recommend_score`).
COLUMNS: tuple[Column, ...] = (
    # identidade
    Column("artist_uri", "str", note="URI canônico do Spotify (perfil dominante após consolidação)"),
    Column("artist_name", "str", note="Nome do artista"),
    Column("country", "str", note="Praça: código ISO de 2 letras, ou 'global' para o chart mundial"),
    # volume e catálogo
    Column("total_tracks", "int", minimum=0, note="Faixas distintas que entraram no chart"),
    Column("total_streams", "float", minimum=0, note="Streams somados na janela da base"),
    Column("entry_count", "int", minimum=0, note="Quantas vezes uma faixa entrou como NEW_ENTRY"),
    # posição
    Column("avg_rank", "float", minimum=1, maximum=200, note="Rank diário médio (penaliza catálogo grande)"),
    Column("best_rank", "float", minimum=1, maximum=200, note="Melhor posição alcançada"),
    Column("days_on_chart_total", "float", minimum=0, note="Maior nº de dias no chart entre as faixas"),
    # trajetória
    Column("first_entry_date", "date", note="Primeira aparição no chart da praça"),
    Column("last_seen_date", "date", note="Última aparição no chart da praça"),
    Column("days_since_last_seen", "int", minimum=0, note="Dias entre last_seen_date e a data de corte"),
    Column("trend_30d", "float", nullable=True, note="Variação de streams 30d vs 30d anteriores"),
    Column("trend_90d", "float", nullable=True, note="Variação de streams 90d vs 90d anteriores"),
    # forma de carreira
    Column("stream_concentration", "float", minimum=0, maximum=1,
           note="Fração dos streams vinda da faixa mais tocada — detector de hit único"),
    Column("country_stream_share", "float", minimum=0, maximum=1,
           note="Fatia dos streams do artista (nas 5 praças) que vem desta praça"),
    # audiência (global, não por praça)
    Column("monthly_listeners", "float", nullable=True, minimum=0,
           note="Ouvintes mensais GLOBAIS — vem de artists.csv, não é por país"),
    Column("peak_listeners", "float", nullable=True, minimum=0, note="Pico histórico de ouvintes mensais"),
    Column("listener_ratio", "float", nullable=True, minimum=0,
           note="monthly_listeners / peak_listeners — está no auge ou já passou"),
    # contexto
    Column("label_mode", "str", note="Gravadora mais frequente nas faixas do artista"),
    Column("merged_uris_count", "int", minimum=1, note="Perfis duplicados do Spotify consolidados nesta linha"),
    # saídas dos modelos
    Column("cluster", "int", minimum=0, note="ID do cluster K-Means (arbitrário entre execuções)"),
    Column("profile", "str", domain=PROFILES, note="Perfil de carreira nomeado por centroide (notebook 03)"),
    Column("trend_status", "str", domain=TREND_STATUSES, note="Leitura de trajetória, descritiva (notebook 03)"),
    Column("recommend_label", "str", domain=RECOMMEND_LABELS, note="Regra de negócio usada como alvo de treino"),
    Column("recommend_score", "float", minimum=0, maximum=100,
           note="P(classe high) x 100 segundo o Random Forest (notebook 02)"),
    # derivadas na carga (não precisam estar no Parquet)
    Column("tier", "str", domain=TIERS, note="Faixa de aposta derivada de recommend_score"),
    Column("is_active", "bool", note="Apareceu no chart nos últimos 90 dias antes da data de corte"),
)

#: Derivadas pelo carregador se ausentes no arquivo.
DERIVED: frozenset[str] = frozenset({"tier", "is_active"})

#: O que o Parquet precisa trazer de fato.
REQUIRED_COLUMNS: tuple[str, ...] = tuple(c.name for c in COLUMNS if c.name not in DERIVED)

COLUMNS_BY_NAME: dict[str, Column] = {c.name: c for c in COLUMNS}


@dataclass
class MetaContract:
    """Formato de `data/api/meta.json`."""

    dataset_version: str
    is_fixture: bool
    reference_date: str  # data de corte dos charts (AAAA-MM-DD)
    window_start: str
    window_end: str
    countries: list[str]
    row_count: int
    model_metrics: dict[str, float] = field(default_factory=dict)
    generated_at: str = ""

    REQUIRED_KEYS = (
        "dataset_version", "is_fixture", "reference_date",
        "window_start", "window_end", "countries", "row_count",
    )
