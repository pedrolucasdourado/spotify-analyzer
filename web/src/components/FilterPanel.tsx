import type { CountItem, Filters, Meta } from "../types";

interface Props {
  meta: Meta;
  filters: Filters;
  counts: { profiles: CountItem[]; trends: CountItem[]; tiers: CountItem[] } | null;
  hiddenByActive: number;
  onChange: (patch: Partial<Filters>) => void;
  onReset: () => void;
}

function toggle(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

function countOf(items: CountItem[] | undefined, value: string): string {
  const hit = items?.find((i) => i.value === value);
  return hit ? String(hit.count) : "";
}

export function FilterPanel({ meta, filters, counts, hiddenByActive, onChange, onReset }: Props) {
  const active =
    filters.q.trim() !== "" ||
    filters.profiles.length > 0 ||
    filters.trends.length > 0 ||
    filters.tiers.length > 0 ||
    !filters.onlyActive;

  return (
    <aside className="filters">
      <div className="fgroup">
        <label className="flabel" htmlFor="busca">
          Buscar artista
        </label>
        <input
          id="busca"
          className="search"
          type="search"
          placeholder="Nome do artista"
          value={filters.q}
          onChange={(e) => onChange({ q: e.target.value })}
        />
      </div>

      <div className="fgroup">
        <span className="flabel">Recência</span>
        <div className="toggle-row">
          <label className="check">
            <input
              type="checkbox"
              checked={filters.onlyActive}
              onChange={(e) => onChange({ onlyActive: e.target.checked })}
            />
            <span>Somente artistas ativos</span>
          </label>
          <p className="hint">
            {filters.onlyActive
              ? `No chart nos 90 dias antes de ${meta.reference_date ?? "a data de corte"}.` +
                (hiddenByActive > 0 ? ` ${hiddenByActive} artistas escondidos.` : "")
              : "Incluindo quem sumiu do chart — 4 de cada 5 artistas da base."}
          </p>
        </div>
      </div>

      <div className="fgroup">
        <span className="flabel">Faixa de aposta</span>
        {meta.tiers.map((t) => (
          <label className="check" key={t.value} title={t.note}>
            <input
              type="checkbox"
              checked={filters.tiers.includes(t.value)}
              onChange={() => onChange({ tiers: toggle(filters.tiers, t.value) })}
            />
            <span>{t.label}</span>
            <span className="cnt">{countOf(counts?.tiers, t.value)}</span>
          </label>
        ))}
      </div>

      <div className="fgroup">
        <span className="flabel">Papel no cartaz</span>
        {meta.profiles.map((p) => (
          <label className="check" key={p.value} title={p.note}>
            <input
              type="checkbox"
              checked={filters.profiles.includes(p.value)}
              onChange={() => onChange({ profiles: toggle(filters.profiles, p.value) })}
            />
            <span>
              {p.role}
              <span className="role-hint">{p.label}</span>
            </span>
            <span className="cnt">{countOf(counts?.profiles, p.value)}</span>
          </label>
        ))}
      </div>

      <div className="fgroup">
        <span className="flabel">Momento</span>
        {meta.trends.map((t) => (
          <label className="check" key={t.value}>
            <input
              type="checkbox"
              checked={filters.trends.includes(t.value)}
              onChange={() => onChange({ trends: toggle(filters.trends, t.value) })}
            />
            <span>{t.label}</span>
            <span className="cnt">{countOf(counts?.trends, t.value)}</span>
          </label>
        ))}
      </div>

      {active && (
        <button type="button" className="linkbtn" onClick={onReset}>
          Limpar filtros
        </button>
      )}
    </aside>
  );
}
