import type { DashboardData, StockResult } from "@/types/dashboard";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";

// Returned when a refresh is already running (HTTP 409). The result will arrive
// over SSE when the in-progress refresh finishes, so this is not an error.
export const REFRESH_IN_PROGRESS = "in_progress" as const;

const _emptyI5 = { today_value: 0, past_values: [], avg: 0, ratio: null, day_count: 0, dates: [], today_date: null };
const _emptyI6 = { is_ath: false, ath_price: null, ath_date: null, days_since_ath: null, year_high: null, year_high_date: null };
const _emptyI7 = { nasdaq_from_open_pct: 0, nasdaq_from_prev_close_pct: 0 };

function migrateStock(s: Record<string, unknown>): StockResult {
  // Old schema: i4 = volume object, i5 = ATH object, i6 = NASDAQ object, gap_up_pct = number
  // New schema: i4 = gap number, i5 = volume object, i6 = ATH object, i7 = NASDAQ object
  const isOld = s.i4 != null && typeof s.i4 === "object" && "today_value" in (s.i4 as object);
  if (isOld) {
    return {
      ...s,
      i4: (s.gap_up_pct as number | null) ?? null,
      i5: (s.i4 as StockResult["i5"]) ?? _emptyI5,
      i6: (s.i5 as StockResult["i6"]) ?? _emptyI6,
      i7: (s.i6 as StockResult["i7"]) ?? _emptyI7,
    } as StockResult;
  }
  // New schema — fill defaults for any missing fields
  return {
    ...s,
    i5: (s.i5 as StockResult["i5"]) ?? _emptyI5,
    i6: (s.i6 as StockResult["i6"]) ?? _emptyI6,
    i7: (s.i7 as StockResult["i7"]) ?? _emptyI7,
  } as StockResult;
}

export function migrateDashboard(d: DashboardData): DashboardData {
  if (!d?.stocks) return d;
  return { ...d, stocks: d.stocks.map((s) => migrateStock(s as unknown as Record<string, unknown>)) };
}

export async function fetchRefresh(): Promise<DashboardData | typeof REFRESH_IN_PROGRESS> {
  const res = await fetch(`${API}/api/v1/refresh`, { method: "POST" });
  if (res.status === 409) return REFRESH_IN_PROGRESS;
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Refresh failed (${res.status}): ${body}`);
  }
  return migrateDashboard(await res.json());
}

export async function fetchLast(): Promise<DashboardData | null> {
  const res = await fetch(`${API}/api/v1/last`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Failed to load last data (${res.status})`);
  return migrateDashboard(await res.json());
}

export interface NewsArticle {
  headline: string;
  summary: string;
  source: string;
  url: string;
  image: string;
  datetime: number;
  category: string;
}

export async function fetchNews(symbol: string): Promise<NewsArticle[]> {
  const res = await fetch(`${API}/api/v1/news/${encodeURIComponent(symbol)}`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.articles ?? [];
}
