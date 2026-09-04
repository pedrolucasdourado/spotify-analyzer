# 🎵 Spotify Artist Recommender for Event Producers

Sistema de recomendação de artistas para produtores de eventos, baseado em dados de performance do Spotify Charts.

## Problema
Produtores de eventos precisam escolher artistas que realmente tenham relevância em um determinado país. Streams ≠ público de show, mas são um forte indicador.

## Abordagem
Pipeline ML híbrido com:
1. **Clustering (K-Means)** — Perfis de carreira: Veterano Consistente, Consolidado, Nicho Recorrente, One-Hit Wonder, Efêmero Cauda Longa, Legado Global
2. **Classificação (Random Forest / XGBoost)** — Score de recomendação 0-100 por artista × país (mede momentum atual, não fama histórica)
3. **EDA** — Análise de mercado, labels, tendências

## Estrutura e ordem de execução

Os notebooks são numerados pela **ordem em que precisam rodar** — `02` depende do `cluster_labels.csv` gerado pelo `01`, então rodar fora de ordem quebra o pipeline.

```
├── notebooks/
│   ├── 00_data_loading.ipynb      # R1 - Pipeline de dados + deduplicação de artistas
│   ├── 01_clustering.ipynb        # R2 - K-Means (perfil de carreira)
│   ├── 02_supervised_model.ipynb  # P1 - Random Forest / XGBoost (score de recomendação)
│   ├── 03_eda.ipynb               # P2 - Análise exploratória (independente do 01/02)
│   └── 04_visualizations.ipynb    # P2 - Dashboard final
├── data/
│   ├── raw/                       # CSVs originais (não versionados)
│   └── processed/                 # Parquets/CSVs gerados (artist_country_features.parquet,
│                                   # cluster_labels.csv, model_results.csv)
├── models/                        # Modelos treinados
├── docs/                          # Gráficos exportados
└── requirements.txt
```

## O que cada etapa resolve (histórico de correções)

O pipeline passou por uma rodada de correções depois que a primeira versão apresentou resultados que não batiam com a realidade (ex. Henrique & Juliano, Guns N' Roses e Taylor Swift mal classificados). Documentado nos próprios notebooks, resumo aqui:

- **Deduplicação de artistas (00, seção 5.1)**: o mesmo artista às vezes tem mais de um `artist_uri` no Spotify (perfil legado/duplicado) — isso fragmentava o sinal do artista principal. Consolidado por `(artist_name, país)`; o notebook mostra a comparação antes/depois (99 grupos, 13.220 → 13.120 linhas).
- **Perfil de carreira sem vazamento (01)**: clustering usa só forma estrutural de carreira (catálogo, streams, dias no chart, concentração, entradas) — nada de `trend`/`rank`/recência, que são a base da regra de `recommend_label` no 02.
- **Correção "fama global vs. chart local" (01, seção 7.1)**: artistas mundialmente consagrados mas com presença de chart pequena/concentrada num país específico (Guns N' Roses, Madonna) caíam em `One-Hit Wonder`/`Efêmero Cauda Longa`. Testamos incluir `monthly_listeners` direto no clustering — piorou o silhouette (métrica global demais, atrapalha a diferenciação por país). Solução: regra de override pós-clustering usando percentil de `monthly_listeners`, criando o 6º perfil `Legado Global` — mas isso sozinho também capturava astros pop **atuais** (Kid LAROI, Benson Boone, Teddy Swims) que só ainda não têm catálogo extenso num país específico. Adicionado um filtro de "tempo de estrada" (`global_first_entry` antes de 2019, ou seja, já chartava desde o início da janela de dados) para só classificar como `Legado Global` quem é catálogo antigo de fato, não breakout recente.
- **Regra de `recommend_label` redefinida (02)**: trocamos `avg_rank ≤ 50` (penalizava catálogo grande — Henrique & Juliano nunca passava) por percentil de `total_streams` dentro do país (top 10% + ativo ≤ 90 dias). Validado contra os artistas reais que dominam cada mercado.
- **Colunas por país, não globais (02)**: `monthly_listeners`/`peak_listeners` vêm de `artists.csv` sem quebra por país; adicionamos `country_stream_share` como sinal genuinamente por país.
- **`recommend_label` (regra) vs. `predicted_label` (modelo) vs. `recommend_score` (probabilidade)**: três colunas separadas no resultado final para não confundir regra de negócio com previsão do modelo.

## Dados
- **charts_songs_daily.csv** (~10GB, 42M linhas) — Rankings diários do Spotify por país
- **artists.csv** (~4MB, 73K artistas) — Monthly listeners

## Métricas atuais (teste, RF / XGBoost)

`low` é 80% da base e `medium` é sistematicamente a classe mais fraca do pipeline — por isso as três classes são reportadas, não só `high` (histórico completo da evolução em [TRAJETORIA.md](TRAJETORIA.md)).

| Classe | RF precisão | RF recall | RF F1 | XGB precisão | XGB recall | XGB F1 |
|---|---|---|---|---|---|---|
| `high` | 0,45 | 0,97 | 0,61 | 0,47 | 0,96 | 0,63 |
| `low` | 0,93 | 0,65 | 0,76 | 0,93 | 0,71 | 0,81 |
| `medium` | 0,27 | 0,60 | 0,37 | 0,31 | 0,60 | 0,41 |
| **macro avg** | 0,55 | 0,74 | 0,58 | 0,57 | 0,76 | 0,62 |
| **weighted avg** | 0,80 | 0,66 | 0,70 | 0,82 | 0,71 | 0,74 |

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
