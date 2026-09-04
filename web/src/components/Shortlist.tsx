import { api } from "../api";
import { chartTime, int, pct, sinceChart, streams } from "../format";
import type { Artist, Filters } from "../types";
import { TierPill, TrendMark } from "./Bits";

interface Props {
  items: Artist[];
  filters: Filters;
  onRemove: (uri: string) => void;
  onClear: () => void;
}

const ROWS: { label: string; render: (a: Artist) => React.ReactNode }[] = [
  { label: "Aposta", render: (a) => <TierPill tier={a.tier} label={a.tier_label} /> },
  { label: "Score", render: (a) => <span className="mono">{Math.round(a.recommend_score)}</span> },
  { label: "Papel no cartaz", render: (a) => a.role },
  { label: "Momento", render: (a) => <TrendMark status={a.trend_status} label={a.trend_label} /> },
  { label: "Praça", render: (a) => a.country.toUpperCase() },
  { label: "Streams na janela", render: (a) => <span className="mono">{streams(a.total_streams)}</span> },
  { label: "Faixas no chart", render: (a) => <span className="mono">{int(a.total_tracks)}</span> },
  { label: "Melhor posição", render: (a) => <span className="mono">{int(a.best_rank)}º</span> },
  { label: "Tempo de estrada", render: (a) => <span className="mono">{chartTime(a.days_on_chart_total)}</span> },
  { label: "Dependência de um hit", render: (a) => <span className="mono">{pct(a.stream_concentration)}</span> },
  { label: "Força nesta praça", render: (a) => <span className="mono">{pct(a.country_stream_share)}</span> },
  { label: "Ouvintes vs. pico", render: (a) => <span className="mono">{pct(a.listener_ratio)}</span> },
  { label: "Última vez no chart", render: (a) => <span className="mono">{sinceChart(a.days_since_last_seen)}</span> },
  { label: "Gravadora", render: (a) => a.label_mode },
];

export function Shortlist({ items, filters, onRemove, onClear }: Props) {
  if (items.length === 0) {
    return (
      <div className="state">
        <h3>Nenhum artista na lista curta</h3>
        <p className="shortlist-empty">
          Use o botão <b>+</b> na tabela de descoberta para juntar nomes aqui. A lista compara os
          artistas lado a lado e vira o CSV que você leva para a reunião. Ela fica salva neste
          navegador.
        </p>
      </div>
    );
  }

  const mixedMarkets = new Set(items.map((i) => i.country)).size > 1;

  return (
    <>
      <div className="resultbar">
        <span className="resultcount">
          {items.length} {items.length === 1 ? "artista" : "artistas"} <span>na lista curta</span>
        </span>
        <div className="spacer" />
        <button type="button" className="linkbtn" onClick={onClear}>
          Esvaziar lista
        </button>
        <a
          className="btn primary"
          href={api.exportUrl(
            { ...filters, onlyActive: false, profiles: [], trends: [], tiers: [], q: "" },
            items.map((i) => i.artist_uri),
          )}
        >
          Baixar CSV
        </a>
      </div>

      {mixedMarkets && (
        <p className="note" style={{ marginBottom: 12 }}>
          A lista tem artistas de praças diferentes. O CSV sai com a praça de cada linha, mas os
          scores só são comparáveis dentro de uma mesma praça.
        </p>
      )}

      <div className="compare">
        <table>
          <thead>
            <tr>
              <th className="rowhead">Artista</th>
              {items.map((a) => (
                <th key={a.artist_uri}>
                  {a.artist_name}
                  <br />
                  <button type="button" className="linkbtn" onClick={() => onRemove(a.artist_uri)}>
                    remover
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ROWS.map((row) => (
              <tr key={row.label}>
                <td className="rowhead">{row.label}</td>
                {items.map((a) => (
                  <td key={a.artist_uri}>{row.render(a)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
