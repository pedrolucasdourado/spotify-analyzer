import type { ArtistDetail, Filters, MarketOverview, Meta, Page } from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "/api";

async function get<T>(path: string, params?: URLSearchParams): Promise<T> {
  const url = params ? `${BASE}${path}?${params}` : `${BASE}${path}`;
  const res = await fetch(url);
  if (!res.ok) {
    let detail = `Erro ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : detail;
    } catch {
      /* resposta sem corpo JSON */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export function filterParams(f: Filters): URLSearchParams {
  const p = new URLSearchParams({ country: f.country });
  if (f.q.trim()) p.set("q", f.q.trim());
  f.profiles.forEach((v) => p.append("profile", v));
  f.trends.forEach((v) => p.append("trend", v));
  f.tiers.forEach((v) => p.append("tier", v));
  p.set("only_active", String(f.onlyActive));
  p.set("sort", f.sort);
  p.set("order", f.order);
  return p;
}

export const api = {
  meta: () => get<Meta>("/meta"),

  artists: (f: Filters, limit: number, offset: number) => {
    const p = filterParams(f);
    p.set("limit", String(limit));
    p.set("offset", String(offset));
    return get<Page>("/artists", p);
  },

  artist: (uri: string, country: string) =>
    get<ArtistDetail>(`/artists/${encodeURIComponent(uri)}`, new URLSearchParams({ country })),

  overview: (country: string) => get<MarketOverview>(`/markets/${country}/overview`),

  exportUrl: (f: Filters, uris?: string[]) => {
    const p = filterParams(f);
    uris?.forEach((u) => p.append("uris", u));
    return `${BASE}/export/artists.csv?${p}`;
  },
};
