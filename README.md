# 🎤 Radar de Line-Up

Curadoria de artistas por praça para produtoras de festivais e shows, a partir dos charts diários do Spotify.

**A tarefa do usuário final:** escolher nomes para um evento numa praça específica, montar uma lista curta para negociar, e justificar a escolha internamente.

> **Ressalva:** streams indicam relevância, não garantem público pagante em show. O score é a probabilidade de um artista atender a uma regra de negócio sobre os charts — não é previsão de bilheteria.

---

## Rodando

### Opção 1 — Docker (um comando)

```bash
docker compose up --build
```

Front em <http://localhost:8080>, API em <http://localhost:8000>, documentação interativa em <http://localhost:8000/docs>.

### Opção 2 — Local

```bash
# API
python -m venv .venv
.venv/Scripts/activate            # Linux/Mac: source .venv/bin/activate
pip install -r api/requirements.txt
uvicorn app.main:app --app-dir api --reload

# Front, em outro terminal
cd web
npm install
npm run dev
```

O front sobe em <http://localhost:5173> e faz proxy de `/api` para a API.

`low` é 80% da base e `medium` é sistematicamente a classe mais fraca do pipeline — por isso as três classes são reportadas, não só `high` (histórico completo da evolução em [TRAJETORIA.md](TRAJETORIA.md)).

| Classe | RF precisão | RF recall | RF F1 | XGB precisão | XGB recall | XGB F1 |
|---|---|---|---|---|---|---|
| `high` | 0,45 | 0,97 | 0,61 | 0,47 | 0,96 | 0,63 |
| `low` | 0,93 | 0,65 | 0,76 | 0,93 | 0,71 | 0,81 |
| `medium` | 0,27 | 0,60 | 0,37 | 0,31 | 0,60 | 0,41 |
| **macro avg** | 0,55 | 0,74 | 0,58 | 0,57 | 0,76 | 0,62 |
| **weighted avg** | 0,80 | 0,66 | 0,70 | 0,82 | 0,71 | 0,74 |
### Testes

```bash
pytest api/tests -q
```

---

## Estado dos dados

O repositório já traz um **dataset-semente** em `data/api/`, para que API e front rodem sem esperar o reprocessamento dos CSVs brutos.

A semente mistura duas origens:

- **Linhas reais**, extraídas das saídas impressas nos notebooks — top BR do 00 e do 02, e a validação de artistas internacionais do 03;
- **Preenchimento sintético**, sorteado a partir dos centroides de cluster e das proporções medidas (80% `low`, 87% `Inativo`, distribuição de perfis 5307/3741/2814/1073/185).

`meta.json` marca `is_fixture: true`, a API expõe essa flag e o front mostra um aviso permanente. **Nenhum número da semente deve ser apresentado como resultado do projeto.**

Para regerar a semente:

```bash
python -m src.pipeline.seed --out data/api --rows 600
```

### Trocando pelo dataset real

Nada no código muda — só o arquivo apontado:

```bash
pip install -r requirements-pipeline.txt

# caminho completo, a partir dos CSVs brutos
python -m src.pipeline.build_dataset --charts charts_songs_daily.csv --artists artists.csv

# caminho curto, se alguém do time ainda tem data/processed/
python -m src.pipeline.build_dataset --from-processed
```

O script grava `data/api/artists.parquet` (com `is_fixture: false`), os modelos em `models/` e os intermediários que os notebooks usam. Ele valida a saída contra o mesmo contrato que a API valida no boot, roda as checagens de sanidade e imprime a distribuição de faixas para calibração.

Para servir outro arquivo sem mexer em código:

```bash
SPOTIFY_DATASET=/caminho/artists.parquet uvicorn app.main:app --app-dir api
```

---

## Arquitetura

**Scoring em lote, API só de leitura.** O modelo roda offline no pipeline e grava um dataset final. A API não importa `scikit-learn` nem `xgboost` e nunca chama `predict` — carrega ~13 mil linhas na memória e responde consultas.

Os dados são um histórico fechado de charts: não há ingestão diária, então não há nada para reescorar em tempo real. Isso mantém o deploy num container sem dependência de ML, e evita expor um endpoint de predição enquanto o modelo ainda não sustenta essa confiança.

```
├── api/
│   ├── app/
│   │   ├── contract.py       # fonte única da verdade sobre o formato do dataset
│   │   ├── validation.py     # valida no boot; falha alto se o dado divergir
│   │   ├── dataset.py        # carga e consulta — único lugar que conhece o Parquet
│   │   ├── labels.py         # tradução de métrica em linguagem de produção
│   │   ├── schemas.py        # respostas
│   │   ├── routers.py        # endpoints
│   │   └── main.py
│   └── tests/
├── web/                      # React + Vite + TypeScript
├── src/pipeline/
│   ├── seed.py               # gerador do dataset-semente
│   └── build_dataset.py      # notebooks 00 -> 03 -> 02 como script
├── notebooks/                # exploração original
├── data/api/                 # dataset servido pela API (vai para o git)
└── models/                   # modelos serializados (regeráveis)
```

`build_dataset.py` roda na ordem **00 → 03 → 02**, que é a dependência real: o modelo supervisionado consome os perfis de carreira do clustering.

---

## Endpoints

| Endpoint | Serve |
|---|---|
| `GET /health` | Sinal de vida e versão do dataset |
| `GET /meta` | Praças, perfis, momentos, faixas, data de corte e métricas do modelo — o front não guarda nenhuma lista fixa |
| `GET /artists` | Lista filtrada e paginada. `country` (obrigatório), `q`, `profile`, `trend`, `tier`, `label`, `only_active`, `min_score`, `max_score`, `sort`, `order`, `limit`, `offset` |
| `GET /artists/{uri}?country=` | Ficha completa com leituras e presença nas cinco praças |
| `GET /artists/{uri}/countries` | Comparação entre praças — leitura de rota de turnê |
| `GET /markets/{country}/overview` | Panorama da praça: KPIs, distribuições, gravadoras |
| `GET /export/artists.csv` | Mesmos filtros, CSV com cabeçalhos em português |

---

## Traduzir métrica em decisão de cartaz

É onde está a maior parte do valor: um produtor não lê `stream_concentration = 0.96`, ele lê "depende de uma música só".

| Coluna | Como aparece na tela |
|---|---|
| `profile` | **Papel no cartaz** — Veterano Consistente → cabeça de cartaz · Consolidado → sub-headliner · Nicho Recorrente → meio de grade · One-Hit Wonder → atração de risco · Efêmero Cauda Longa → sem lastro |
| `trend_status` | **Momento** — em ascensão, estável, em declínio, possível retomada, inativo |
| `stream_concentration` | **Dependência de um hit** (acima de 0,8 vira alerta na ficha) |
| `listener_ratio` | **Está no auge ou já passou** |
| `days_on_chart_total` | **Tempo de estrada no chart** |
| `entry_count` | **Faixas que emplacaram** |
| `country_stream_share` | **Força nesta praça** |

### O score vira faixa, não número

Com precisão de 0,50 na classe `high`, exibir "94,77" comunicaria uma exatidão que o modelo não tem.

| Faixa | Score | Leitura |
|---|---|---|
| Aposta forte | ≥ 85 | Sustenta cabeça de cartaz na praça |
| Boa aposta | 60–84 | Meio de grade sólido, cachê mais negociável |
| Aposta de risco | 30–59 | Só com um motivo além do dado |
| Sem lastro | < 30 | A base não sustenta a escolha |

Os cortes estão em `api/app/contract.py` (`TIER_CUTS`) e **ainda precisam ser calibrados** contra a distribuição real de score — `build_dataset.py` imprime a distribuição e os percentis no fim da execução.

---

## Limitações, e o que o produto faz com elas

| O que os números mostram | Tratamento |
|---|---|
| Precisão 0,50 na classe `high`; F1 macro 0,61 (RF) e 0,63 (XGB) no teste | Faixas em vez de número cru; streams e melhor posição sempre ao lado, para conferência |
| Classe `medium` com F1 entre 0,40 e 0,43 | `predicted_label` não sai da API nem aparece na tela — só a probabilidade |
| 80% da base é `low`; 87% está `Inativo` | Filtro "somente ativos" ligado por padrão, com contagem do que foi escondido |
| `monthly_listeners` é global, não por praça | Rotulado como "ouvintes mensais (global)", com a fatia da praça ao lado |
| `days_since_last_seen` é relativo a 28/05/2026 | Data de corte carimbada no cabeçalho e nas fichas, lida do `meta.json` |
| O score mede uma regra de negócio, não bilheteria | Ressalva permanente e a aba "Como ler o score" dentro do produto |
| IDs de cluster mudam entre execuções | Perfis nomeados por centroide, nunca por ID; o mapa da execução vai para `models/clustering.joblib` |

---

## Notebooks

A exploração original continua em `notebooks/`, e é onde as decisões foram tomadas e documentadas:

| Notebook | Conteúdo |
|---|---|
| `00_data_loading.ipynb` | Carga com Dask, engenharia de atributos, consolidação de perfis duplicados |
| `01_eda.ipynb` | Análise exploratória, mercado, gravadoras |
| `02_supervised_model.ipynb` | Random Forest / XGBoost, diagnóstico e remoção do vazamento |
| `03_clustering.ipynb` | K-Means, nomeação por centroide, `trend_status` |
| `04_visualizations.ipynb` | Gráficos finais |

## Equipe

| Membro | Modo | Responsabilidade |
|---|---|---|
| P1 | Presencial | Modelo supervisionado · empacotamento |
| P2 | Presencial | EDA, visualizações, front |
| R1 | Remoto | Data pipeline · API |
| R2 | Remoto | Clustering · documentação |
