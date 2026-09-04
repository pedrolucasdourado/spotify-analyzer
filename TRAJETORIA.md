# Trajetória do Modelo — Histórico de Decisões e Correções

Este documento reconstrói, em ordem cronológica, como o pipeline de recomendação de artistas (clustering + modelo supervisionado) evoluiu: o que foi encontrado errado, por que, o que foi mudado, e como as métricas se moveram a cada etapa. Fontes: histórico de commits (`git log`) e as células documentadas nos notebooks.

## Linha do tempo dos commits

| Commit | Data | O que entrou |
|---|---|---|
| `11aec92` | 2026-09-01 | `docs: add readme` — README inicial do projeto |
| `405e3bc` | 2026-09-01 | `feat: adiciona os requirements de projeto e notebook 00` — pipeline de carga (Dask sobre `charts_songs_daily.csv`, ~10GB/42M linhas) |
| `cf62483` | 2026-09-03 | `feat: completa o pipeline de análise com EDA, clustering, modelo e visualizações` — notebooks 01–04, figuras, deduplicação de `artist_uri` |
| `21cdddf` | 2026-09-03 | `feat: reordena notebooks pela dependência do pipeline e corrige perfis de carreira` — `01` clustering / `03` EDA, perfil `Legado Global`, README |
| `11bc338` | 2026-09-03 | `fix: restringe Legado Global a artistas com catálogo antigo` — filtro `global_first_entry < 2019` |

Os commits de 2026-09-03 agrupam várias rodadas de investigação — detalhadas abaixo, porque a granularidade do que mudou (e por quê) não aparece nas mensagens de commit.

## Estado inicial (antes das correções)

O notebook `02_supervised_model.ipynb` treinava Random Forest / XGBoost com F1 **1.00 no teste**. A regra do `recommend_label` usava `days_since_last_seen` e `avg_rank`, e essas colunas (mais `best_rank`, `trend_30d`, `trend_90d`) também entravam em `X`. O `dropna` nas features derrubava 13.220 → ~1.440 linhas e apagava a classe `low`.

O clustering (`03_clustering.ipynb`) existia só como esqueleto: nenhuma célula executada, nomes `'TODO_ANALISAR'`. A EDA já gerava histogramas de métricas-chave cujos picos nas bordas pareciam outlier.

---

## Rodada 1 — EDA e o F1 = 1.00 (antes de o vazamento ser corrigido)

Ainda com o modelo vazado, a EDA foi o primeiro recorte: entender o que as métricas-chave realmente medem, e só depois diagnosticar o 100% no relatório de classificação.

### Histogramas “estranhos” não eram outlier

Os gráficos de `stream_concentration` (One-Hit Detector), `listener_ratio` (current/peak) e `days_since_last_seen` tinham colunas verticais que pareciam erro. A unidade de cada ponto é **artista × país** (~13.220 linhas: BR, US, GB, MX, AR). Os picos são **massa no limite da métrica**, não pontos anômalos.

| Métrica | Pico | O que é |
|---|---|---|
| `stream_concentration` | 1.0 (~7 mil linhas) | 100% dos streams de chart vêm de **uma faixa**. A maioria só chartou uma música (one-hit, feat., viral único). Concentração = 1 **não** prova “one-hit wonder” cultural. |
| `listener_ratio` | 1.0 | `monthly_listeners == peak_listeners` (no auge agora, ou pico atualizado). Muitos `NaN` no `artists.csv`; o histograma é só quem tem dado. |
| `days_since_last_seen` | 0 e ~3500 | 0 = esteve no chart no **último dia** da base. ~3500 = chartou no começo da janela (~2017) e não voltou — efeito de início da coleta, não idade real da carreira. |
| `log(streams)` | “bonito” | Único histograma em forma de sino, porque `log1p` comprime a cauda. |

O cálculo estava certo. O título “One-Hit Detector” é agressivo demais para o que a fórmula captura.

### Veteranos com mais de 3000 dias no chart BR

Incluída no notebook de EDA (então `01_eda.ipynb`, hoje `03_eda.ipynb`) a lista de artistas do Brasil com carreira no chart acima de 3000 dias.

- `career_span_days` = última aparição − primeira aparição no Top 200 do Brasil
- Janela da base: **2017-01-01 → 2026-05-28 (3434 dias)**
- **130 artistas (3,9% dos 3.300 do BR)**; 55 ainda estavam no chart no último dia
- Gráfico `docs/eda_veterans_br.png`: top 20 por streams nesse recorte — Henrique & Juliano, Marília Mendonça, Gusttavo Lima, Zé Neto & Cristiano, Jorge & Mateus

### O 100% não era overfitting — era vazamento de target

O F1 = 1.00 **no teste** quase nunca é overfit clássico (isso seria treino alto e teste baixo). O modelo estava **decorando a regra do próprio label**.

A regra era:

- `high` se `days_since_last_seen ≤ 90` **e** `avg_rank ≤ 50`
- `low` se `days_since_last_seen > 180`
- `medium` o resto

…e `days_since_last_seen`, `avg_rank`, `best_rank`, `trend_30d`, `trend_90d` iam para o `X`. O `dropna` derrubava **13.220 → ~1.440 linhas** e **apagava a classe `low`**, porque `trend_90d` é NaN exatamente em quem sumiu. No teste restavam 11 `high` e 277 `medium` — um problema trivial.

**Mudanças** em `02_supervised_model.ipynb`:

1. Fora do modelo: qualquer coluna usada na regra (ou que a reproduza)
2. Imputação (`SimpleImputer` mediana) no lugar de dropar linha — base volta às 13.220 linhas, 3 classes
3. RF regularizada: `max_depth=6`, `min_samples_leaf=20`, `min_samples_split=40`
4. Relatório de treino vs teste vs CV 5-fold

Accuracy no `classification_report` não tem linha por classe porque é uma pergunta sobre o conjunto inteiro (“de todas as linhas, quantas receberam o rótulo certo?”). Precision e recall nascem de um recorte um-contra-o-resto; o resumo delas é `macro avg` / `weighted avg`.

**Resultado** (ainda com a regra `avg_rank ≤ 50`):

| | Treino | Teste |
|---|---|---|
| F1 weighted | 0,77 | 0,76 |
| Acurácia | 0,74 | 0,73 |
| CV F1 macro | 0,48 ± 0,01 | |
| Recall `high` | 0,98 | 0,54 |
| Precisão `high` | — | ~0,05 |

Treino e teste ficaram parecidos. O 100% era o bug; ~73% de acurácia é o modelo honesto. A classe `high` continuava difícil (**67** linhas, ~0,5%) — gargalo do **rótulo raro**, não do volume do CSV de charts.

**Detalhamento por classe (teste), as três classes — não só `high`:**

| Classe | Support | RF precisão | RF recall | RF F1 | XGB precisão | XGB recall | XGB F1 |
|---|---|---|---|---|---|---|---|
| `high` | 13 | 0,05 | 0,54 | 0,09 | 0,09 | 0,54 | 0,15 |
| `low` | 2117 | 0,91 | 0,77 | 0,83 | 0,91 | 0,78 | 0,84 |
| `medium` | 514 | 0,42 | 0,59 | 0,49 | 0,43 | 0,63 | 0,53 |
| **macro avg** | 2644 | 0,46 | 0,65 | 0,47 | 0,48 | 0,65 | 0,50 |
| **weighted avg** | 2644 | 0,81 | 0,73 | 0,76 | 0,82 | 0,75 | 0,77 |

`low` puxa o `weighted avg` pra cima só porque é 80% da base (support 2117 de 2644) — isso é o motivo de reportar `macro avg` também: ele trata as três classes com peso igual, e é onde fica visível que `high` (F1 0,09–0,15) e `medium` (F1 0,49–0,53) estão bem mais fracas do que `low` (F1 0,83–0,84) sozinho sugeriria.

Ainda restavam problemas: sem perfil de carreira no modelo, `recommend_label` no CSV final era só a regra de negócio (sem `predicted_label` separado), e o top BR da recomendação não batia com o mercado.

---

## Rodada 2 — Perfil de carreira como feature

**Pergunta:** o `recommend_score` deveria depender do perfil de carreira (Rising Star, One-Hit Wonder, Veterano, etc.)?

**Descobertas:** existiam dois conceitos chamados “label”: `label_mode` (gravadora — Sony, Universal — usado só na EDA) e o perfil de carreira do clustering (mencionado no README, nunca implementado). `03_clustering.ipynb` nunca tinha rodado.

**Mudanças:**

1. Clustering do zero (K-Means, k=5 por elbow/silhouette), com features **sem** `trend`/`rank`/recência para não reintroduzir o vazamento da Rodada 1: `total_tracks`, `total_streams` (log), `days_on_chart_total`, `stream_concentration`, `entry_count`
2. 5 perfis pelos centróides: Veterano Consistente, Consolidado, Nicho Recorrente, One-Hit Wonder, Efêmero Cauda Longa
3. `cluster_labels.csv` mergeado como one-hot no `02`
4. `country_stream_share` (fração do streaming do artista **naquele país**) — `monthly_listeners`/`peak_listeners` são globais, copiados em cada linha de país
5. `SimpleImputer(add_indicator=True)`
6. Colunas separadas: `recommend_label` (regra / ground truth) vs `predicted_label` (saída do RF)

**Resultado:** impacto pequeno nas métricas (`profile_Efemero_Cauda_Longa` chegou a 7ª feature da RF). O problema maior — a regra do target — ainda não tinha sido tocado.

| Classe | Support | RF precisão | RF recall | RF F1 | XGB precisão | XGB recall | XGB F1 |
|---|---|---|---|---|---|---|---|
| `high` | 13 | 0,05 | 0,62 | 0,09 | 0,08 | 0,54 | 0,15 |
| `low` | 2117 | 0,91 | 0,76 | 0,83 | 0,91 | 0,80 | 0,85 |
| `medium` | 514 | 0,42 | 0,59 | 0,49 | 0,46 | 0,63 | 0,53 |
| **macro avg** | 2644 | 0,46 | 0,65 | 0,47 | 0,49 | 0,66 | 0,51 |
| **weighted avg** | 2644 | 0,81 | 0,73 | 0,76 | 0,82 | 0,77 | 0,79 |

Praticamente idêntico à Rodada 1 — o perfil de carreira ajudou um pouco o recall de `high` (0,54 → 0,62 na RF), mas `medium` continuou o ponto fraco (F1 ~0,49–0,53), e a regra do target (não a falta de feature) seguia sendo o gargalo real.

---

## Rodada 3 — “Os resultados do Brasil não condizem com a realidade”

**Sintoma:** MC Menor ZL, MC GH Original e DJ JZ no topo das recomendações do Brasil; Henrique & Juliano, Marília Mendonça e Gusttavo Lima quase não apareciam.

**Causa 1 — `avg_rank` penaliza catálogo grande.** Média não ponderada do rank diário de **toda a carreira, todas as faixas**. Henrique & Juliano (212 faixas) `avg_rank` 97,8; Marília Mendonça (171) 86,4; Ana Castela (100) 79,9 — nenhum passava em `avg_rank ≤ 50`. Artista com 2–3 faixas que estreou no topo passava fácil.

**Causa 2 — identidade de artista fragmentada.** O mesmo nome às vezes tem mais de um `artist_uri` no Spotify. Henrique & Juliano: um perfil de 212 faixas e outro quase morto de 2, no mesmo país. 99 grupos (199 linhas) via `(artist_name, país)`.

**Mudanças:**

1. `recommend_label` passa a **percentil de `total_streams` dentro do país** (`streams_pct ≥ 0.90`, top 10% + recência ≤ 90 dias). Validado: o top BR passa a trazer quem de fato domina o mercado.
2. Deduplicação em `00_data_loading.ipynb` (seção 5.1): soma streams/faixas/entradas, `avg_rank` ponderado por `days_on_chart_total`, datas min/max, URI canônico = perfil com mais streams. **13.220 → 13.120 linhas**
3. Clustering e modelo reexecutados na base deduplicada

**Bug no meio:** IDs do KMeans mudam de ordem entre reruns. O mapa fixo `{4: 'Veterano Consistente', ...}` classificou Taylor Swift e Henrique & Juliano como Efêmero Cauda Longa. Corrigido com **nomeação automática a partir dos centróides** (separar concentrados de diversificados, depois ordenar por escala).

**Resultado:**

| Métrica (teste) | Random Forest | XGBoost |
|---|---|---|
| F1 macro | 0,6110 | 0,6340 |
| Precisão `high` | 0,50 | 0,51 |
| Recall `high` | 0,93 | 0,92 |

| Classe | Support | RF precisão | RF recall | RF F1 | XGB precisão | XGB recall | XGB F1 |
|---|---|---|---|---|---|---|---|
| `high` | 143 | 0,50 | 0,93 | 0,65 | 0,51 | 0,92 | 0,66 |
| `low` | 2098 | 0,94 | 0,67 | 0,78 | 0,93 | 0,73 | 0,82 |
| `medium` | 383 | 0,29 | 0,66 | 0,40 | 0,32 | 0,62 | 0,43 |
| **macro avg** | 2624 | 0,58 | 0,75 | 0,61 | 0,59 | 0,76 | 0,63 |
| **weighted avg** | 2624 | 0,82 | 0,68 | 0,72 | 0,82 | 0,72 | 0,75 |

Salto grande em relação à Rodada 2 — a causa raiz era a regra do target, não falta de feature. Vale reparar que o salto não veio de graça: `low` perdeu recall (0,77→0,67 na RF) porque agora é uma classe bem maior e mais heterogênea (a régua de "ativo nos últimos 90 dias" não mudou, mas o corte de streams sim), e `medium` segue sendo a classe mais fraca (F1 0,40–0,43) — o modelo ainda confunde bastante `medium` com `low`, o que faz sentido: são artistas de popularidade intermediária, mais difíceis de separar do que os extremos.

---

## Rodada 4 — Guns N' Roses classificado como “One-Hit Wonder”

**Sintoma:** bandas mundialmente consagradas (Guns N' Roses, Queen, Madonna) em `One-Hit Wonder`/`Efêmero Cauda Longa` com score baixo.

**Causa:** o clustering só enxerga o chart **daquele país**. Guns N' Roses tem 1–4 faixas circulando no Top 200 por país (picos virais de catálogo antigo), então cai nos clusters de catálogo pequeno/concentrado, mesmo com ~40M ouvintes mensais globais.

**Tentativa 1 (descartada):** incluir `monthly_listeners` nas features do K-Means. Silhouette 0,39 → 0,27 — métrica global (idêntica nas 5 linhas de país do mesmo artista), atrapalha a diferenciação por país.

**Tentativa 2 (parcial):** override pós-clustering — top ~7% de `monthly_listeners` global **e** perfil `One-Hit Wonder`/`Efêmero Cauda Longa` → 6º perfil **`Legado Global`**. Corrigiu Guns N' Roses, Queen, Madonna (143 linhas, 1,09%).

**Problema da tentativa 2:** a regra também capturou astros pop **atuais** — The Kid LAROI, Benson Boone, Teddy Swims, sombr — fama global alta sem catálogo extenso *naquele país*. Confundia “consagrado” com “em ascensão”.

**Correção final:** filtro de tempo de estrada — `global_first_entry` (data mais antiga no chart, entre os 5 países) **< 2019-01-01**. Bandas de catálogo (Beatles, AC/DC, Guns N' Roses, The Police) já apareciam no dia 1 dos dados (2017). Astros atuais entram entre 2019 e 2025. `Legado Global` exige as duas condições: 108 linhas (eram 143).

> Limitação: não existe o ano real de estreia na base, só quando o artista entrou *neste* chart (começa em 2017). Tradeoff aceito: prioriza não confundir “consagrado” com “em ascensão”.

`profile` = quem é o artista. `recommend_score` = vale reservar **agora**. Guns N' Roses pode ser `Legado Global` com score baixo — é o desenho, não um erro.

**Resultado:** mudança pequena nas métricas (~1% das linhas), correção qualitativa na interpretabilidade dos perfis.

| Métrica (teste) | Random Forest | XGBoost |
|---|---|---|
| F1 macro | 0,5824 | 0,6156 |
| Precisão `high` | 0,45 | 0,47 |
| Recall `high` | 0,97 | 0,96 |

| Classe | Support | RF precisão | RF recall | RF F1 | XGB precisão | XGB recall | XGB F1 |
|---|---|---|---|---|---|---|---|
| `high` | 143 | 0,45 | 0,97 | 0,61 | 0,47 | 0,96 | 0,63 |
| `low` | 2098 | 0,93 | 0,65 | 0,76 | 0,93 | 0,71 | 0,81 |
| `medium` | 383 | 0,27 | 0,60 | 0,37 | 0,31 | 0,60 | 0,41 |
| **macro avg** | 2624 | 0,55 | 0,74 | 0,58 | 0,57 | 0,76 | 0,62 |
| **weighted avg** | 2624 | 0,80 | 0,66 | 0,70 | 0,82 | 0,71 | 0,74 |

Aqui fica visível o que a métrica só de `high` escondia: mover ~1% das linhas para `Legado Global` custou recall de `low` (0,67→0,65) e principalmente **F1 de `medium`** (0,40→0,37 na RF) — a classe mais fraca do pipeline ficou um pouco mais fraca ainda. É um preço pequeno mas real pago por uma correção que não tinha objetivo nenhum de mexer nessa métrica (era sobre interpretabilidade do perfil, não sobre separar `medium` de `low`).

---

## Rodada 5 — Reordenação, deduplicação no notebook e cache do Jupyter

**Pedidos:** (1) a deduplicação de artistas dentro do notebook 00, com antes/depois; (2) notebooks numerados pela ordem real de execução; (3) README no estado atual.

**Mudanças:**

1. `00_data_loading.ipynb` reexecutado com a consolidação de `artist_uri` na seção 5.1, imprimindo o antes/depois (Henrique & Juliano: 2 linhas fragmentadas → 1 consolidada)
2. Notebooks renomeados pela dependência real:

   | Antes | Depois | Motivo |
   |---|---|---|
   | `03_clustering.ipynb` | `01_clustering.ipynb` | Precisa rodar **antes** do 02 (que consome `cluster_labels.csv`) |
   | `01_eda.ipynb` | `03_eda.ipynb` | Independente do 01/02; não é pré-requisito do modelo |
   | `02_supervised_model.ipynb` | (mesmo nome) | Continua precisando do 00 e do 01 |

3. README com a estrutura nova, o histórico de correções resumido e as métricas atuais

**Cache do 04:** o dashboard continuava mostrando classificação antiga depois das correções. Causa: Jupyter congela a **saída** (Plotly/matplotlib) no momento da execução. O `04` lia CSVs já certos, mas não tinha sido reexecutado. Resolvido rodando de novo — sem mudança de código.

> Qualquer notebook consumidor downstream precisa ser **reexecutado**, não só ter o fonte corrigido, quando uma correção muda os dados upstream. Ordem: 00 → 01 → 02 → 03 → 04.

---

## Métricas — evolução completa

F1 macro/weighted resume tudo num número, mas esconde qual classe está puxando o resultado. A tabela abaixo mostra o **F1-score por classe** (`high`, `low`, `medium`) em cada rodada — não só `high` — porque `low` é 80% da base (domina qualquer média ponderada) e `medium` é sistematicamente a classe mais fraca do pipeline, algo que nenhuma das métricas agregadas usadas até aqui deixava óbvio.

| Etapa | RF F1 `high` | RF F1 `low` | RF F1 `medium` | RF F1 macro | XGB F1 `high` | XGB F1 `low` | XGB F1 `medium` | XGB F1 macro |
|---|---|---|---|---|---|---|---|---|
| Estado inicial (vazamento, F1 no teste = 1.00) | ~1,00 | ~1,00 | ~1,00 | ~1,00 | ~1,00 | ~1,00 | ~1,00 | ~1,00 |
| Rodada 1 — features honestas, regra `avg_rank ≤ 50` | 0,09 | 0,83 | 0,49 | 0,4713 | 0,15 | 0,84 | 0,53 | 0,5008 |
| Rodada 2 — perfil de carreira | 0,09 | 0,83 | 0,49 | 0,4718 | 0,15 | 0,85 | 0,53 | 0,5106 |
| Rodada 3 — dedup + regra por percentil | 0,65 | 0,78 | 0,40 | 0,6110 | 0,66 | 0,82 | 0,43 | 0,6340 |
| Rodada 4 — `Legado Global` + filtro de vintage | 0,61 | 0,76 | 0,37 | 0,5824 | 0,63 | 0,81 | 0,41 | 0,6156 |

Leituras que só aparecem olhando `low` e `medium` junto com `high`:

- **`medium` nunca foi bem resolvido em nenhuma rodada** (F1 entre 0,37 e 0,53) — é consistentemente a classe mais fraca do pipeline, mais até que `high` a partir da Rodada 3. Faz sentido: `medium` é definida por exclusão ("nem claramente `high`, nem claramente `low`"), então é onde as duas classes vizinhas mais se confundem.
- **`low` é a classe "de graça"** (F1 sempre ≥ 0,76) porque é 80% da base — qualquer modelo, mesmo ruim, acerta a maioria dela. É por isso que reportar só acurácia ou F1 weighted mascara os problemas nas outras duas classes.
- O ganho da Rodada 3 (trocar a regra do target) veio de melhorar `high` **e** manter `low`/`medium` relativamente estáveis — não foi só "high melhorou às custas do resto". Já a Rodada 4 (`Legado Global`) teve um custo real e mensurável em `low` e principalmente `medium` (F1 caiu em ambos), pago por uma correção de interpretabilidade que não tinha meta nenhuma sobre separar essas duas classes.
- Na Rodada 1 o número que importa não é o F1 macro: é o F1 weighted ~0,76 com treino ≈ teste (o 100% era o vazamento).

---

## Correções que NÃO foram feitas (limitações conhecidas)

- **`avg_rank` ponderado por streams na fonte:** a correção estruturalmente mais correta para o viés de catálogo seria recalcular `avg_rank` nos dados diários brutos (`charts_songs_daily.csv`, ~10GB/42M linhas). Não foi feito porque exigiria reprocessar o CSV via Dask, e a máquina esteve com pouca memória (swap quase cheio). Mitigado pela regra em percentil de `total_streams`.
- **Ano real de estreia do artista:** não está nos dados (só quando ele entrou neste chart, que começa em 2017). `global_first_entry < 2019` é aproximação.
- **`stream_concentration` pós-deduplicação:** média ponderada por streams entre os perfis consolidados, não recalculada por faixa.

---

## Arquivos-chave do pipeline final

- [`00_data_loading.ipynb`](notebooks/00_data_loading.ipynb) — carga + feature engineering + deduplicação de `artist_uri` (seção 5.1)
- [`01_clustering.ipynb`](notebooks/01_clustering.ipynb) — K-Means (5 perfis estruturais) + override `Legado Global` (seção 7.1) → `cluster_labels.csv`
- [`02_supervised_model.ipynb`](notebooks/02_supervised_model.ipynb) — Random Forest/XGBoost, regra de `recommend_label` por percentil → `model_results.csv`
- [`03_eda.ipynb`](notebooks/03_eda.ipynb) — análise exploratória (independente)
- [`04_visualizations.ipynb`](notebooks/04_visualizations.ipynb) — dashboard final (reexecutar após mudança upstream)
- [`README.md`](README.md) — visão geral e ordem de execução
