const nf = new Intl.NumberFormat("pt-BR");

/** Streams em bilhão/milhão/mil — um produtor lê a ordem de grandeza, não o dígito. */
export function streams(value: number): string {
  if (value >= 1e9) return `${(value / 1e9).toFixed(1).replace(".", ",")} bi`;
  if (value >= 1e6) return `${(value / 1e6).toFixed(1).replace(".", ",")} mi`;
  if (value >= 1e3) return `${(value / 1e3).toFixed(0)} mil`;
  return nf.format(Math.round(value));
}

export function pct(value: number | null): string {
  return value === null || Number.isNaN(value) ? "—" : `${Math.round(value * 100)}%`;
}

export function int(value: number | null): string {
  return value === null || Number.isNaN(value) ? "—" : nf.format(Math.round(value));
}

/** Tempo no chart em anos/meses; dias crus não dizem nada a quem monta grade. */
export function chartTime(days: number): string {
  if (days >= 365) {
    const years = days / 365;
    return `${years.toFixed(1).replace(".", ",")} anos`;
  }
  if (days >= 30) return `${Math.round(days / 30)} meses`;
  return `${Math.round(days)} dias`;
}

export function sinceChart(days: number): string {
  if (days === 0) return "No chart";
  if (days < 30) return `${days} d atrás`;
  if (days < 365) return `${Math.round(days / 30)} m atrás`;
  return `${(days / 365).toFixed(1).replace(".", ",")} a atrás`;
}

export function isoDate(value: string | null): string {
  if (!value) return "—";
  const [y, m, d] = value.split("-");
  return `${d}/${m}/${y}`;
}
