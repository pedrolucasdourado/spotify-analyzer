import type { Artist } from "../types";
import { chartTime, int, pct, sinceChart, streams } from "../format";
import { TierPill, TrendMark } from "./Bits";

interface Props {
  items: Artist[];
  picked: Set<string>;
  onOpen: (artist: Artist) => void;
  onTogglePick: (artist: Artist) => void;
}

export function ArtistTable({ items, picked, onOpen, onTogglePick }: Props) {
  return (
    <div className="tablewrap">
      <table>
        <thead>
          <tr>
            <th style={{ width: 36 }}>
              <span className="visually-hidden" aria-hidden="true">
                +
              </span>
            </th>
            <th>Artista</th>
            <th>Aposta</th>
            <th>Papel no cartaz</th>
            <th>Momento</th>
            <th className="num">Streams</th>
            <th className="num">Melhor pos.</th>
            <th className="num">Estrada</th>
            <th className="num">Hit único</th>
            <th className="num">Força aqui</th>
            <th className="num">Última vez</th>
          </tr>
        </thead>
        <tbody>
          {items.map((a) => {
            const on = picked.has(a.artist_uri);
            return (
              <tr key={a.artist_uri} className={on ? "picked" : undefined}>
                <td>
                  <button
                    type="button"
                    className={`pickbtn${on ? " on" : ""}`}
                    aria-pressed={on}
                    title={on ? "Tirar da lista curta" : "Juntar à lista curta"}
                    onClick={() => onTogglePick(a)}
                  >
                    {on ? "✓" : "+"}
                  </button>
                </td>
                <td>
                  <button type="button" className="linkname" onClick={() => onOpen(a)}>
                    <span className="namecell">
                      <b>{a.artist_name}</b>
                      <span>{a.label_mode}</span>
                    </span>
                  </button>
                </td>
                <td>
                  <TierPill tier={a.tier} label={a.tier_label} />
                </td>
                <td>{a.role}</td>
                <td>
                  <TrendMark status={a.trend_status} label={a.trend_label} />
                </td>
                <td className="num mono">{streams(a.total_streams)}</td>
                <td className="num mono">{int(a.best_rank)}º</td>
                <td className="num mono">{chartTime(a.days_on_chart_total)}</td>
                <td className="num mono">{pct(a.stream_concentration)}</td>
                <td className="num mono">{pct(a.country_stream_share)}</td>
                <td className="num mono">{sinceChart(a.days_since_last_seen)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
