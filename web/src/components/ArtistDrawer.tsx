import { useEffect, useState } from "react";
import { api } from "../api";
import { chartTime, int, isoDate, pct, streams } from "../format";
import type { ArtistDetail } from "../types";
import { Bar, TierPill, TrendMark } from "./Bits";

interface Props {
  artistUri: string;
  country: string;
  picked: boolean;
  onTogglePick: (detail: ArtistDetail) => void;
  onClose: () => void;
}

export function ArtistDrawer({ artistUri, country, picked, onTogglePick, onClose }: Props) {
  const [detail, setDetail] = useState<ArtistDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setDetail(null);
    setError(null);
    api
      .artist(artistUri, country)
      .then((d) => alive && setDetail(d))
      .catch((e: Error) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [artistUri, country]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <>
      <button type="button" className="scrim" aria-label="Fechar ficha" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label="Ficha do artista">
        {error && (
          <div className="state error">
            <h3>Não deu para abrir a ficha</h3>
            <p>{error}</p>
          </div>
        )}

        {!detail && !error && <div className="state">Carregando ficha…</div>}

        {detail && (
          <>
            <div className="drawer-head">
              <h2>{detail.artist_name}</h2>
              <button type="button" className="closebtn" onClick={onClose} aria-label="Fechar">
                ×
              </button>
            </div>
            <p className="roleline">
              {detail.role} · {detail.profile} · {detail.label_mode}
            </p>

            <div className="scoreblock">
              <span className="num mono">{Math.round(detail.recommend_score)}</span>
              <div>
                <TierPill tier={detail.tier} label={detail.tier_label} />
                <div className="txt">{detail.tier_note}</div>
              </div>
            </div>
            <p className="note" style={{ margin: "8px 0 0" }}>
              O score é a probabilidade que o modelo dá de este artista atender ao critério de
              relevância da praça. Não é previsão de bilheteria.
            </p>

            <section className="sec">
              <h4>Leitura</h4>
              <ul className="readings">
                {detail.readings.map((r, i) => (
                  <li key={i} className={r.level}>
                    {r.text}
                  </li>
                ))}
              </ul>
              <p className="note">{detail.role_note}</p>
            </section>

            <section className="sec">
              <h4>Momento</h4>
              <TrendMark status={detail.trend_status} label={detail.trend_label} />
            </section>

            <section className="sec">
              <h4>Números da praça</h4>
              <dl className="metrics">
                <div>
                  <dt>Streams na janela</dt>
                  <dd>{streams(detail.total_streams)}</dd>
                </div>
                <div>
                  <dt>Faixas no chart</dt>
                  <dd>{int(detail.total_tracks)}</dd>
                </div>
                <div>
                  <dt>Faixas que emplacaram</dt>
                  <dd>{int(detail.entry_count)}</dd>
                </div>
                <div>
                  <dt>Melhor posição</dt>
                  <dd>{int(detail.best_rank)}º</dd>
                </div>
                <div>
                  <dt>Tempo de estrada</dt>
                  <dd>{chartTime(detail.days_on_chart_total)}</dd>
                </div>
                <div>
                  <dt>Dependência de um hit</dt>
                  <dd>{pct(detail.stream_concentration)}</dd>
                </div>
                <div>
                  <dt>Ouvintes mensais (global)</dt>
                  <dd>{detail.monthly_listeners ? streams(detail.monthly_listeners) : "—"}</dd>
                </div>
                <div>
                  <dt>Ouvintes vs. pico</dt>
                  <dd>{pct(detail.listener_ratio)}</dd>
                </div>
                <div>
                  <dt>Primeira vez no chart</dt>
                  <dd style={{ fontSize: 14 }}>{isoDate(detail.first_entry_date)}</dd>
                </div>
                <div>
                  <dt>Última vez no chart</dt>
                  <dd style={{ fontSize: 14 }}>{isoDate(detail.last_seen_date)}</dd>
                </div>
              </dl>
              <p className="note">
                Ouvintes mensais vêm do perfil global do Spotify — o mesmo número vale para as
                cinco praças. Para força local, use “Streams na janela” e a comparação abaixo.
              </p>
            </section>

            <section className="sec">
              <h4>Força por praça</h4>
              <div className="presence">
                {detail.presence.map((p) => (
                  <div
                    key={p.country}
                    className={`prow${p.country === country ? " here" : ""}`}
                  >
                    <span className="pname">{p.country_name}</span>
                    <Bar value={p.country_stream_share} accent={p.country === country} />
                    <span className="pv mono">{pct(p.country_stream_share)}</span>
                  </div>
                ))}
              </div>
              <p className="note">
                {detail.presence.length > 1
                  ? "Fatia do streaming do artista que vem de cada praça da base — leitura de rota de turnê."
                  : "Este artista só aparece no chart desta praça dentro da base."}
              </p>
            </section>

            <section className="sec">
              <button
                type="button"
                className={`btn${picked ? "" : " primary"}`}
                onClick={() => onTogglePick(detail)}
              >
                {picked ? "Tirar da lista curta" : "Juntar à lista curta"}
              </button>
            </section>
          </>
        )}
      </aside>
    </>
  );
}
