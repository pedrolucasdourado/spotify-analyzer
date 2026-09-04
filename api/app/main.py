"""Radar de Line-Up — API de leitura.

Escolha de arquitetura (ver o plano do MVP): o scoring roda offline, no
pipeline. Esta API não importa sklearn nem xgboost e nunca chama
`predict` — ela carrega o Parquet resultante na memória e responde
consultas. São ~13 mil linhas de histórico fechado; não há o que
reescorar em tempo real.

Rodar:
    uvicorn app.main:app --reload --app-dir api
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .dataset import Dataset, set_dataset
from .routers import DISCLAIMER, router

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("radar")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Carregando dataset de %s", settings.dataset_path)
    ds = Dataset.load()
    set_dataset(ds)
    log.info(
        "Dataset '%s' carregado: %d linhas, %d artistas%s",
        ds.meta.get("dataset_version"),
        len(ds.df),
        ds.meta["artist_count"],
        "  [SEMENTE — dados de demonstração]" if ds.meta.get("is_fixture") else "",
    )
    yield


app = FastAPI(
    title="Radar de Line-Up",
    version="0.1.0",
    summary="Curadoria de artistas por praça para produtoras de festivais e shows.",
    description=(
        "Serve os resultados do pipeline `spotify-analyzer` (charts do Spotify, "
        "2017–2026) traduzidos para linguagem de produção de evento.\n\n"
        f"**Ressalva:** {DISCLAIMER}"
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins if o.strip()],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(router)
