"""Configuração da API por variável de ambiente."""

from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _path_from_env(var: str, default: Path) -> Path:
    raw = os.getenv(var)
    return Path(raw).expanduser().resolve() if raw else default


class Settings:
    """Trocar a semente pelo dataset real é apontar SPOTIFY_DATASET."""

    def __init__(self) -> None:
        self.dataset_path: Path = _path_from_env(
            "SPOTIFY_DATASET", _REPO_ROOT / "data" / "api" / "artists.parquet"
        )
        self.meta_path: Path = _path_from_env(
            "SPOTIFY_META", self.dataset_path.parent / "meta.json"
        )
        self.cors_origins: list[str] = os.getenv(
            "SPOTIFY_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
        self.max_page_size: int = int(os.getenv("SPOTIFY_MAX_PAGE_SIZE", "200"))
        self.max_export_rows: int = int(os.getenv("SPOTIFY_MAX_EXPORT_ROWS", "5000"))
        #: Falhar o boot se o dataset não cumprir o contrato. Desligue só para
        #: inspecionar um arquivo suspeito localmente.
        self.strict_contract: bool = os.getenv("SPOTIFY_STRICT_CONTRACT", "1") != "0"


settings = Settings()
