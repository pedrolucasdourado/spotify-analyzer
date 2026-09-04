import { useEffect, useState } from "react";
import { api } from "../api";
import { int, streams } from "../format";
import type { CountItem, MarketOverview } from "../types";
import { Bar } from "./Bits";

function Distribution({ items, accent }: { items: CountItem[]; accent?: boolean }) {
  const max = Math.max(1, ...items.map((i) => i.count));
  return (
    <>
      {items.map((i) => (
        <div className="distrow" key={i.value}>
          <span>{i.label}</span>
          <Bar value={i.count / max} accent={accent} />
          <span className="dv mono">{int(i.count)}</span>
        </div>
      ))}
    </>
  );
}

export function Overview({ country }: { country: string }) {
  const [data, setData] = useState<MarketOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setData(null);
    setError(null);
    api
      .overview(country)
      .then((d) => alive && setData(d))
      .catch((e: Error) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [country]);

  if (error) {
    return (
      <div className="state error">
        <h3>Não deu para carregar o panorama</h3>
        <p>{error}</p>
      </div>
    );
  }
  if (!data) return <div className="state">Carregando panorama…</div>;

  const maxLabel = Math.max(1, ...data.top_labels.map((l) => l.streams));

  return (
    <>
      <dl className="kpis">
        <div className="kpi">
          <dt>Artistas na praça</dt>
          <dd>{int(data.artists)}</dd>
        </div>
        <div className="kpi">
          <dt>Ativos</dt>
          <dd>{int(data.active_artists)}</dd>
        </div>
        <div className="kpi">
          <dt>Streams na janela</dt>
          <dd>{streams(data.total_streams)}</dd>
        </div>
        <div className="kpi">
          <dt>Mediana entre ativos</dt>
          <dd>{data.median_streams_active ? streams(data.median_streams_active) : "—"}</dd>
        </div>
      </dl>

      <div className="panels">
        <div className="panel">
          <h3>Faixa de aposta</h3>
          <Distribution items={data.tiers} accent />
          <p className="note">
            A base inteira, sem filtro de recência. A concentração em “sem lastro” é esperada: a
            maior parte dos artistas do chart teve passagem curta.
          </p>
        </div>

        <div className="panel">
          <h3>Perfis de carreira</h3>
          <Distribution items={data.profiles} />
        </div>

        <div className="panel">
          <h3>Momento</h3>
          <Distribution items={data.trends} />
          <p className="note">
            Quase todo mundo aparece como inativo porque a janela de atividade tem 90 dias e a base
            cobre nove anos de chart.
          </p>
        </div>

        <div className="panel">
          <h3>Gravadoras por streams</h3>
          {data.top_labels.map((l) => (
            <div className="distrow" key={l.label}>
              <span title={l.label}>{l.label}</span>
              <Bar value={l.streams / maxLabel} />
              <span className="dv mono">{streams(l.streams)}</span>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
