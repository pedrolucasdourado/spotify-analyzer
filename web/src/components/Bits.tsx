import type { Tier } from "../types";

export function TierPill({ tier, label }: { tier: Tier; label: string }) {
  return <span className={`pill ${tier}`}>{label}</span>;
}

const TREND_CLASS: Record<string, string> = {
  "Em Ascensao": "up",
  "Em Declinio": "down",
  Estavel: "flat",
  "Possivel Retomada": "flat",
  Inativo: "off",
};

export function TrendMark({ status, label }: { status: string; label: string }) {
  return <span className={`trend ${TREND_CLASS[status] ?? "off"}`}>{label}</span>;
}

export function Bar({ value, accent = false }: { value: number; accent?: boolean }) {
  const width = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div className="bar">
      <i className={accent ? "accent" : undefined} style={{ width: `${width}%` }} />
    </div>
  );
}
