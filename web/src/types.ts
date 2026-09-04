export type Tier = "forte" | "boa" | "risco" | "sem_lastro";

export interface Artist {
  artist_uri: string;
  artist_name: string;
  country: string;
  recommend_score: number;
  tier: Tier;
  tier_label: string;
  profile: string;
  role: string;
  trend_status: string;
  trend_label: string;
  is_active: boolean;
  total_streams: number;
  total_tracks: number;
  entry_count: number;
  best_rank: number;
  days_on_chart_total: number;
  stream_concentration: number;
  country_stream_share: number;
  listener_ratio: number | null;
  monthly_listeners: number | null;
  label_mode: string;
  days_since_last_seen: number;
}

export interface Reading {
  metric: string;
  level: "ok" | "atencao" | "alerta" | "info";
  text: string;
}

export interface Presence {
  country: string;
  country_name: string;
  recommend_score: number;
  tier: Tier;
  tier_label: string;
  profile: string;
  role: string;
  total_streams: number;
  country_stream_share: number;
  is_active: boolean;
}

export interface ArtistDetail extends Artist {
  avg_rank: number;
  peak_listeners: number | null;
  first_entry_date: string | null;
  last_seen_date: string | null;
  merged_uris_count: number;
  cluster: number;
  recommend_label: string;
  role_note: string;
  tier_note: string;
  readings: Reading[];
  presence: Presence[];
}

export interface Page {
  total: number;
  limit: number;
  offset: number;
  items: Artist[];
}

export interface CountryOption {
  code: string;
  name: string;
  artists: number;
  active_artists: number;
}

export interface Meta {
  dataset_version: string;
  is_fixture: boolean;
  fixture_notice: string | null;
  reference_date: string | null;
  window_start: string | null;
  window_end: string | null;
  row_count: number;
  artist_count: number;
  countries: CountryOption[];
  profiles: { value: string; label: string; role: string; note: string }[];
  trends: { value: string; label: string }[];
  tiers: { value: Tier; label: string; note: string; min_score: number }[];
  sort_options: { value: string; label: string }[];
  model_metrics: Record<string, number>;
  model_used_for_score: string | null;
  disclaimer: string;
}

export interface CountItem {
  value: string;
  label: string;
  count: number;
}

export interface MarketOverview {
  country: string;
  country_name: string;
  artists: number;
  active_artists: number;
  total_streams: number;
  median_streams_active: number | null;
  profiles: CountItem[];
  trends: CountItem[];
  tiers: CountItem[];
  top_labels: { label: string; streams: number; artists: number }[];
  top_artists: Artist[];
}

export interface Filters {
  country: string;
  q: string;
  profiles: string[];
  trends: string[];
  tiers: string[];
  onlyActive: boolean;
  sort: string;
  order: "asc" | "desc";
}
