"""Testes mínimos da API, rodando contra o dataset-semente."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.contract import PILOT_COUNTRIES, PROFILES, TIERS  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["rows"] > 0


def test_meta_traz_dominios_para_os_filtros(client):
    body = client.get("/meta").json()
    codes = [c["code"] for c in body["countries"]]
    assert set(codes) >= set(PILOT_COUNTRIES)
    assert all(c["name"] and c["name"] != c["code"] for c in body["countries"]), \
        "toda praça precisa de um nome legível para o seletor com busca"
    assert [p["value"] for p in body["profiles"]] == list(PROFILES)
    assert [t["value"] for t in body["tiers"]] == list(TIERS)
    assert body["reference_date"]
    assert body["disclaimer"]


def test_filtro_de_praca_devolve_so_aquela_praca(client):
    body = client.get("/artists", params={"country": "br", "limit": 100}).json()
    assert body["items"]
    assert {i["country"] for i in body["items"]} == {"br"}


def test_praca_inexistente_da_422(client):
    # 'zz' não é código ISO atribuído — e, diferente de 'pt', não vira uma
    # praça real quando a base cresce.
    r = client.get("/artists", params={"country": "zz"})
    assert r.status_code == 422
    assert "zz" in r.json()["detail"]


def test_ordenacao_por_score_e_decrescente(client):
    items = client.get("/artists", params={"country": "br", "limit": 50}).json()["items"]
    scores = [i["recommend_score"] for i in items]
    assert scores == sorted(scores, reverse=True)


def test_ordenacao_por_melhor_posicao_poe_os_melhores_primeiro(client):
    items = client.get(
        "/artists", params={"country": "br", "sort": "best_rank", "limit": 30}
    ).json()["items"]
    ranks = [i["best_rank"] for i in items]
    assert ranks == sorted(ranks), "melhor posição é menor número — desc deve trazer os menores"


def test_only_active_ligado_por_padrao(client):
    padrao = client.get("/artists", params={"country": "br", "limit": 200}).json()
    assert all(i["is_active"] for i in padrao["items"])

    tudo = client.get(
        "/artists", params={"country": "br", "only_active": "false", "limit": 200}
    ).json()
    assert tudo["total"] > padrao["total"], "sem o filtro tem que sobrar mais gente"


def test_filtro_por_perfil(client):
    body = client.get(
        "/artists",
        params={"country": "br", "profile": "Veterano Consistente", "only_active": "false"},
    ).json()
    assert body["items"]
    assert {i["profile"] for i in body["items"]} == {"Veterano Consistente"}
    assert {i["role"] for i in body["items"]} == {"Cabeça de cartaz"}


def test_perfil_invalido_da_422(client):
    r = client.get("/artists", params={"country": "br", "profile": "Rising Star"})
    assert r.status_code == 422


def test_busca_por_nome_ignora_acento_e_caixa(client):
    body = client.get(
        "/artists", params={"country": "br", "q": "marilia", "only_active": "false"}
    ).json()
    assert any("Marília" in i["artist_name"] for i in body["items"])


def test_paginacao_nao_repete_itens(client):
    p1 = client.get("/artists", params={"country": "br", "limit": 5, "offset": 0}).json()
    p2 = client.get("/artists", params={"country": "br", "limit": 5, "offset": 5}).json()
    assert p1["total"] == p2["total"]
    assert not ({i["artist_uri"] for i in p1["items"]} & {i["artist_uri"] for i in p2["items"]})


def test_detalhe_traz_leituras_e_presenca(client):
    item = client.get("/artists", params={"country": "br", "limit": 1}).json()["items"][0]
    detail = client.get(
        f"/artists/{item['artist_uri']}", params={"country": "br"}
    ).json()
    assert detail["artist_name"] == item["artist_name"]
    assert detail["readings"], "a ficha precisa de pelo menos uma leitura"
    assert any(p["country"] == "br" for p in detail["presence"])
    assert "predicted_label" not in detail, "classe prevista não vai para a tela"


def test_artista_inexistente_da_404(client):
    r = client.get("/artists/spotify:artist:naoexiste", params={"country": "br"})
    assert r.status_code == 404


def test_overview_da_praca(client):
    body = client.get("/markets/br/overview").json()
    assert body["country_name"] == "Brasil"
    assert body["artists"] >= body["active_artists"]
    assert sum(p["count"] for p in body["profiles"]) == body["artists"]
    assert body["top_artists"]


def test_export_csv_sai_com_cabecalho_em_portugues(client):
    r = client.get("/export/artists.csv", params={"country": "br", "limit": 10})
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    linhas = r.text.splitlines()
    assert linhas[0].lstrip("﻿").startswith("Artista;Praça;Score do modelo")
    assert len(linhas) > 1


def test_export_aceita_lista_curta(client):
    items = client.get("/artists", params={"country": "br", "limit": 3}).json()["items"]
    uris = [i["artist_uri"] for i in items]
    r = client.get("/export/artists.csv", params={"country": "br", "uris": uris})
    assert len(r.text.splitlines()) == len(uris) + 1
