import type { DashboardData } from "@/types/dashboard";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";

export async function fetchRefresh(): Promise<DashboardData> {
  const res = await fetch(`${API}/api/v1/refresh`, { method: "POST" });
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
