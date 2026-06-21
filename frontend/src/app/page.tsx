"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import CandidatesTable from "@/components/CandidatesTable";
import MarketBar from "@/components/MarketBar";
import RefreshButton from "@/components/RefreshButton";
import { fetchLast, fetchRefresh, REFRESH_IN_PROGRESS } from "@/lib/api";
import type { DashboardData } from "@/types/dashboard";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const refreshingRef = useRef(false);

  const runRefresh = useCallback(async () => {
    if (refreshingRef.current) return;
    refreshingRef.current = true;
    setRefreshing(true);
    setError(null);
    try {
      const result = await fetchRefresh();
      if (result === REFRESH_IN_PROGRESS) return;
      setData(result);
      setRefreshing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setRefreshing(false);
    } finally {
      refreshingRef.current = false;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchLast()
      .then((d) => {
        if (!cancelled && d) setData(d);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    const url = `${API}/api/v1/events`;
    const es = new EventSource(url);

    es.addEventListener("refresh_start", () => {
      setRefreshing(true);
    });

    es.addEventListener("refresh_done", (e: MessageEvent) => {
      try {
        const parsed = JSON.parse(e.data) as DashboardData;
        if (parsed.stocks) setData(parsed);
      } catch { /* ignore parse errors */ }
      setRefreshing(false);
    });

    es.addEventListener("events_update", (e: MessageEvent) => {
      try {
        const eventsMap = JSON.parse(e.data) as Record<string, {
          next_earnings_date?: string | null;
          next_dividend_date?: string | null;
          ex_dividend_date?: string | null;
          market_cap?: number | null;
        }>;
        setData((prev) => {
          if (!prev?.stocks) return prev;
          return {
            ...prev,
            stocks: prev.stocks.map((s) => {
              const ev = eventsMap[s.symbol];
              return ev ? { ...s, ...ev } : s;
            }),
          };
        });
      } catch { /* ignore */ }
    });

    es.addEventListener("status", (e: MessageEvent) => {
      try {
        const status = JSON.parse(e.data);
        if (status.is_refreshing) setRefreshing(true);
      } catch { /* ignore */ }
    });

    es.onerror = () => {
      setRefreshing(false);
    };

    return () => es.close();
  }, []);

  const emptyNasdaq = { rt_level: 0, open_level: 0, prev_close: 0, from_open_pct: 0, from_prev_close_pct: 0, error: null };
  const showInitialLoading = refreshing && data === null;

  return (
    <div className="min-h-screen flex flex-col" style={{ background: "var(--bg)" }}>
      {/* Header — centered branding, compact refresh */}
      <header
        className="flex flex-col items-center px-4 sm:px-6 pt-safe pb-3 sm:pb-4 border-b"
        style={{ background: "var(--surface)", borderColor: "var(--border)" }}
      >
        <div className="flex items-center gap-3 w-full justify-center">
          <h1
            className="text-2xl sm:text-3xl font-bold tracking-[0.25em]"
            style={{ color: "var(--text-bright)" }}
          >
            SFM
          </h1>
          <RefreshButton loading={refreshing} onClick={runRefresh} />
        </div>
        <p className="text-xs sm:text-sm mt-1 italic" style={{ color: "var(--muted)" }}>
          Patience compounds; conviction endures.
        </p>
      </header>

      {/* NASDAQ bar */}
      <MarketBar
        nasdaq={data?.nasdaq ?? emptyNasdaq}
        refreshedAt={data?.refreshed_at ?? null}
        refreshing={refreshing}
        marketSession={data?.market_session ?? null}
      />

      {/* Main content */}
      <main className="flex-1 p-4 sm:p-5 pb-safe space-y-4">
        {error && (
          <div
            className="px-4 py-3 rounded text-sm"
            style={{ background: "#3a1a1a", border: "1px solid #5c2020", color: "#f0a0a0" }}
          >
            <strong>Error:</strong> {error}
            {data && (
              <span className="ml-2" style={{ color: "#d08080" }}>Showing last good data below.</span>
            )}
          </div>
        )}

        {showInitialLoading && (
          <div
            className="px-4 py-3 rounded text-sm"
            style={{ background: "#1a2010", border: "1px solid #2a3a18", color: "#b0c090" }}
          >
            Fetching top 10 candidates + historical data… ~20–40 seconds.
          </div>
        )}

        <CandidatesTable stocks={data?.stocks ?? []} />

        {/* Indicator legend */}
        <div
          className="rounded p-4 text-sm space-y-1"
          style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
        >
          <p className="font-medium mb-2" style={{ color: "var(--muted)" }}>Indicator Reference</p>
          <p className="mb-2" style={{ color: "var(--muted)", fontSize: 12 }}>
            Close = real-time price during session · official closing price after market close · tap any indicator to see its formula
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-1" style={{ color: "var(--muted)" }}>
            <span><span style={{ color: "var(--text)" }}>I1</span> — Close vs Open: (close − open) / open</span>
            <span><span style={{ color: "var(--text)" }}>I2</span> — Close vs Prev Close: (close − prev close) / prev close</span>
            <span><span style={{ color: "var(--text)" }}>I3</span> — Close in Candle: (close − open) / (high − open) · 1.0 = at high, 0 = at open</span>
            <span><span style={{ color: "var(--text)" }}>I4</span> — Gap Up %: (open − prev close) / prev close · overnight move before market opens</span>
            <span><span style={{ color: "var(--text)" }}>I5</span> — 15-day trading value history + today (highlighted) · yellow if &gt;1.5× avg</span>
            <span><span style={{ color: "var(--text)" }}>I6</span> — all-time high + 52-week high · next earnings countdown</span>
            <span><span style={{ color: "var(--text)" }}>I7</span> — NASDAQ % change (shown in table footer)</span>
          </div>
        </div>
      </main>
    </div>
  );
}
