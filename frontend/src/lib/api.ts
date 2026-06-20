import type { DashboardData } from "@/types/dashboard";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";

// Returned when a refresh is already running (HTTP 409). The result will arrive
// over SSE when the in-progress refresh finishes, so this is not an error.
export const REFRESH_IN_PROGRESS = "in_progress" as const;

export async function fetchRefresh(): Promise<DashboardData | typeof REFRESH_IN_PROGRESS> {
  const res = await fetch(`${API}/api/v1/refresh`, { method: "POST" });
  if (res.status === 409) return REFRESH_IN_PROGRESS;
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Refresh failed (${res.status}): ${body}`);
  }
  return res.json();
}

export async function fetchLast(): Promise<DashboardData | null> {
  const res = await fetch(`${API}/api/v1/last`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Failed to load last data (${res.status})`);
  return res.json();
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
