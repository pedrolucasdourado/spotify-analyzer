# 🎵 Spotify Artist Recommender for Event Producers

Sistema de recomendação de artistas para produtores de eventos, baseado em dados de performance do Spotify Charts.

## Problema
Produtores de eventos precisam escolher artistas que realmente tenham relevância em um determinado país. Streams ≠ público de show, mas são um forte indicador.

## Abordagem
Pipeline ML híbrido com:
1. **Clustering (K-Means)** — Perfis de carreira: Rising Star, Veteran, One-Hit Wonder, Comeback, Em Declínio
2. **Classificação (Random Forest / XGBoost)** — Score de recomendação 0-100 por artista × país
3. **EDA** — Análise de mercado, labels, tendências

## Estrutura
```
├── notebooks/
│   ├── 00_data_loading.ipynb      # R1 - Pipeline de dados
│   ├── 01_eda.ipynb               # P2 - Análise exploratória
│   ├── 02_supervised_model.ipynb  # P1 - Random Forest / XGBoost
│   ├── 03_clustering.ipynb        # R2 - K-Means
│   └── 04_visualizations.ipynb    # P2 - Dashboard final
├── data/
│   ├── raw/                       # CSVs originais (não versionados)
│   └── processed/                 # Parquets gerados
├── models/                        # Modelos treinados
├── docs/                          # Gráficos exportados
└── requirements.txt
```

## Dados
- **charts_songs_daily.csv** (~10GB, 42M linhas) — Rankings diários do Spotify por país
- **artists.csv** (~4MB, 73K artistas) — Monthly listeners

## Equipe
| Membro | Modo | Responsabilidade |
|---|---|---|
| P1 | Presencial | Modelo supervisionado |
| P2 | Presencial | EDA + Visualizações + Slides |
| R1 | Remoto | Data pipeline |
| R2 | Remoto | Clustering + Documentação |

## Setup
```bash
pip install -r requirements.txt
```

## ⚠️ Disclaimer
Esta é uma análise de dados de streaming. Ouvintes de streaming não são garantia de público em shows.
