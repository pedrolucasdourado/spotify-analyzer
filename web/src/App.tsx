import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { ArtistDrawer } from "./components/ArtistDrawer";
import { ArtistTable } from "./components/ArtistTable";
import { CountryPicker } from "./components/CountryPicker";
import { FilterPanel } from "./components/FilterPanel";
import { HowToRead } from "./components/HowToRead";
import { Overview } from "./components/Overview";
import { Shortlist } from "./components/Shortlist";
import { int } from "./format";
import type { Artist, Filters, MarketOverview, Meta, Page } from "./types";

const PAGE_SIZE = 50;
const SHORTLIST_KEY = "radar-lineup:shortlist:v1";

function loadShortlist(): Artist[] {
  try {
    const raw = localStorage.getItem(SHORTLIST_KEY);
    return raw ? (JSON.parse(raw) as Artist[]) : [];
  } catch {
    return [];
  }
}

type Tab = "descoberta" | "lista" | "panorama" | "como-ler";

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);

  const [filters, setFilters] = useState<Filters>({
    country: "br",
    q: "",
    profiles: [],
    trends: [],
    tiers: [],
    onlyActive: true,
    sort: "score",
    order: "desc",
  });

  const [tab, setTab] = useState<Tab>("descoberta");
  const [page, setPage] = useState<Page | null>(null);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [openUri, setOpenUri] = useState<string | null>(null);
  const [shortlist, setShortlist] = useState<Artist[]>(loadShortlist);
  const [marketCounts, setMarketCounts] = useState<MarketOverview | null>(null);

  // -- carga inicial
  useEffect(() => {
    api
      .meta()
      .then((m) => {
        setMeta(m);
        if (!m.countries.some((c) => c.code === filters.country) && m.countries[0]) {
          setFilters((f) => ({ ...f, country: m.countries[0].code }));
        }
      })
      .catch((e: Error) => setBootError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // -- lista
  useEffect(() => {
    if (!meta) return;
    let alive = true;
    setLoading(true);
    setListError(null);
    const timer = setTimeout(() => {
      api
        .artists(filters, PAGE_SIZE, offset)
        .then((p) => alive && setPage(p))
        .catch((e: Error) => alive && setListError(e.message))
        .finally(() => alive && setLoading(false));
    }, filters.q ? 220 : 0); // pequeno atraso só na digitação
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [meta, filters, offset]);

  // -- contagens da praça, para os rótulos dos filtros
  useEffect(() => {
    if (!meta) return;
    let alive = true;
    api
      .overview(filters.country)
      .then((o) => alive && setMarketCounts(o))
      .catch(() => alive && setMarketCounts(null));
    return () => {
      alive = false;
    };
  }, [meta, filters.country]);

  useEffect(() => {
    localStorage.setItem(SHORTLIST_KEY, JSON.stringify(shortlist));
  }, [shortlist]);

  const patchFilters = useCallback((patch: Partial<Filters>) => {
    setFilters((f) => ({ ...f, ...patch }));
    setOffset(0);
  }, []);

  const resetFilters = useCallback(() => {
    setFilters((f) => ({ ...f, q: "", profiles: [], trends: [], tiers: [], onlyActive: true }));
    setOffset(0);
  }, []);

  const togglePick = useCallback((artist: Artist) => {
    setShortlist((list) =>
      list.some((a) => a.artist_uri === artist.artist_uri && a.country === artist.country)
        ? list.filter((a) => !(a.artist_uri === artist.artist_uri && a.country === artist.country))
        : [...list, artist],
    );
  }, []);

  const pickedUris = useMemo(
    () => new Set(shortlist.filter((a) => a.country === filters.country).map((a) => a.artist_uri)),
    [shortlist, filters.country],
  );

  const hiddenByActive = useMemo(() => {
    if (!marketCounts || !filters.onlyActive) return 0;
    return marketCounts.artists - marketCounts.active_artists;
  }, [marketCounts, filters.onlyActive]);

  if (bootError) {
    return (
      <div className="app">
        <div className="main">
          <div className="state error">
            <h3>A API não respondeu</h3>
            <p>
              {bootError}. Suba a API com <code>uvicorn app.main:app --app-dir api</code> e recarregue
              esta página.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (!meta) return <div className="state">Carregando…</div>;

  const country = meta.countries.find((c) => c.code === filters.country);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <strong>Radar de Line-Up</strong>
          <span>Curadoria de artistas por praça</span>
        </div>

        <CountryPicker
          countries={meta.countries}
          value={filters.country}
          onChange={(code) => patchFilters({ country: code })}
        />

        <div className="topbar-right">
          <div className="stamp">
            Dados de chart até <b>{meta.window_end}</b>
            <br />
            {int(meta.row_count)} linhas · versão {meta.dataset_version}
          </div>
        </div>
      </header>

      {meta.is_fixture && (
        <div className="banner">
          <b>Semente</b>
          <span>
            {meta.fixture_notice ??
              "Dados de demonstração. Não apresente estes números como resultado."}
          </span>
        </div>
      )}

      <nav className="tabs">
        <button
          type="button"
          className="tab"
          aria-selected={tab === "descoberta"}
          onClick={() => setTab("descoberta")}
        >
          Descoberta
        </button>
        <button
          type="button"
          className="tab"
          aria-selected={tab === "lista"}
          onClick={() => setTab("lista")}
        >
          Lista curta
          {shortlist.length > 0 && <span className="badge">{shortlist.length}</span>}
        </button>
        <button
          type="button"
          className="tab"
          aria-selected={tab === "panorama"}
          onClick={() => setTab("panorama")}
        >
          Panorama da praça
        </button>
        <button
          type="button"
          className="tab"
          aria-selected={tab === "como-ler"}
          onClick={() => setTab("como-ler")}
        >
          Como ler o score
        </button>
      </nav>

      {tab === "descoberta" ? (
        <div className="body">
          <FilterPanel
            meta={meta}
            filters={filters}
            counts={marketCounts}
            hiddenByActive={hiddenByActive}
            onChange={patchFilters}
            onReset={resetFilters}
          />

          <main className="main">
            <div className="resultbar">
              <span className="resultcount">
                {page ? int(page.total) : "—"}{" "}
                <span>
                  {page?.total === 1 ? "artista" : "artistas"} em {country?.name}
                </span>
              </span>

              <div className="spacer" />

              <label className="flabel" htmlFor="ordenar" style={{ marginBottom: 0 }}>
                Ordenar por
              </label>
              <select
                id="ordenar"
                className="sort"
                value={filters.sort}
                onChange={(e) => patchFilters({ sort: e.target.value })}
              >
                {meta.sort_options.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>

              <a className="btn" href={api.exportUrl(filters)}>
                Baixar CSV
              </a>
            </div>

            {listError && (
              <div className="state error">
                <h3>Não deu para carregar a lista</h3>
                <p>{listError}</p>
              </div>
            )}

            {!listError && loading && !page && <div className="state">Carregando artistas…</div>}

            {!listError && page && page.items.length === 0 && (
              <div className="state">
                <h3>Nenhum artista com esses filtros</h3>
                <p>
                  {filters.onlyActive
                    ? "Tente desmarcar “somente artistas ativos” — a maior parte da base saiu do chart há mais de 90 dias."
                    : "Afrouxe os filtros de faixa, papel ou momento."}
                </p>
              </div>
            )}

            {!listError && page && page.items.length > 0 && (
              <>
                <ArtistTable
                  items={page.items}
                  picked={pickedUris}
                  onOpen={(a) => setOpenUri(a.artist_uri)}
                  onTogglePick={togglePick}
                />
                <div className="pager">
                  <button
                    type="button"
                    className="btn"
                    disabled={offset === 0}
                    onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                  >
                    Anteriores
                  </button>
                  <span className="mono">
                    {offset + 1}–{Math.min(offset + PAGE_SIZE, page.total)} de {int(page.total)}
                  </span>
                  <button
                    type="button"
                    className="btn"
                    disabled={offset + PAGE_SIZE >= page.total}
                    onClick={() => setOffset(offset + PAGE_SIZE)}
                  >
                    Próximos
                  </button>
                </div>
              </>
            )}
          </main>
        </div>
      ) : (
        <main className="main">
          {tab === "lista" && (
            <Shortlist
              items={shortlist}
              filters={filters}
              onRemove={(uri) => setShortlist((l) => l.filter((a) => a.artist_uri !== uri))}
              onClear={() => setShortlist([])}
            />
          )}
          {tab === "panorama" && <Overview country={filters.country} />}
          {tab === "como-ler" && <HowToRead meta={meta} />}
        </main>
      )}

      {openUri && (
        <ArtistDrawer
          artistUri={openUri}
          country={filters.country}
          picked={pickedUris.has(openUri)}
          onTogglePick={togglePick}
          onClose={() => setOpenUri(null)}
        />
      )}
    </div>
  );
}
