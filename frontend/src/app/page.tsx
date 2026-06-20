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
  const [debug, setDebug] = useState(false);
  const refreshingRef = useRef(false);

  // Manual refresh (button click). The backend enforces single-flight: if a
  // refresh (cron or another tab) is already running it returns 409, and the
  // result arrives over SSE — so we keep the indicator on and wait, no error.
  const runRefresh = useCallback(async () => {
    if (refreshingRef.current) return;
    refreshingRef.current = true;
    setRefreshing(true);
    setError(null);
    try {
      const result = await fetchRefresh();
      if (result === REFRESH_IN_PROGRESS) {
        // Another refresh owns the lock; SSE will deliver refresh_done. Leave
        // the indicator on; the SSE handler flips it off when data arrives.
        return;
      }
      setData(result);
      setRefreshing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setRefreshing(false);
    } finally {
      refreshingRef.current = false;
    }
  }, []);

  // On open: load persisted snapshot so the screen is never blank.
  useEffect(() => {
    let cancelled = false;
    fetchLast()
      .then((d) => {
        if (!cancelled && d) setData(d);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  // SSE: listen for backend-driven refresh events (scheduler or another tab's
  // manual click). EventSource auto-reconnects on disconnect.
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

    es.addEventListener("status", (e: MessageEvent) => {
      try {
        const status = JSON.parse(e.data);
        if (status.is_refreshing) setRefreshing(true);
      } catch { /* ignore */ }
    });

    es.onerror = () => {
      // EventSource will auto-reconnect; just clear the indicator while
      // disconnected so the UI doesn't show a stale "Updating…".
      setRefreshing(false);
    };

    return () => es.close();
  }, []);

  const emptyNasdaq = { rt_level: 0, open_level: 0, prev_close: 0, from_open_pct: 0, from_prev_close_pct: 0, error: null };
  const showInitialLoading = refreshing && data === null;

  return (
    <div className="min-h-screen flex flex-col" style={{ background: "var(--bg)" }}>
      {/* Header */}
      <header
        className="flex items-center justify-between gap-3 px-4 sm:px-6 pt-safe pb-4 sm:pb-5 border-b"
        style={{ background: "var(--surface)", borderColor: "var(--border)" }}
      >
        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-wide" style={{ color: "var(--text-bright)" }}>
            SFM
          </h1>
          <p className="text-sm mt-0.5 italic" style={{ color: "var(--muted)" }}>
            Patience compounds; conviction endures.
          </p>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <button
            onClick={() => setDebug((d) => !d)}
            className={`hidden sm:block px-3 py-2 rounded text-sm font-medium border transition-colors ${
              debug
                ? "bg-amber-500/20 border-amber-500/50 text-amber-300"
                : "border-transparent text-transparent"
            }`}
            style={debug ? {} : { color: "var(--border)", borderColor: "var(--border)" }}
          >
            {debug ? "Debug ON" : "Debug"}
          </button>
          <RefreshButton loading={refreshing} onClick={runRefresh} />
        </div>
      </header>

      {/* NASDAQ bar */}
      <MarketBar
        nasdaq={data?.nasdaq ?? emptyNasdaq}
        refreshedAt={data?.refreshed_at ?? null}
        refreshing={refreshing}
        debug={debug}
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

        <CandidatesTable stocks={data?.stocks ?? []} debug={debug} />

        {/* Indicator legend */}
        <div
          className="rounded p-4 text-sm space-y-1"
          style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
        >
          <p className="font-medium mb-2" style={{ color: "var(--muted)" }}>Indicator Reference</p>
          <p className="mb-2" style={{ color: "var(--muted)", fontSize: 12 }}>
            Close = real-time price during session · official closing price after market close
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-1" style={{ color: "var(--muted)" }}>
            <span><span style={{ color: "var(--text)" }}>I1</span> — Candle Body: (close − open) / open</span>
            <span><span style={{ color: "var(--text)" }}>I2</span> — Full-Day Gain: (close − prev close) / prev close</span>
            <span><span style={{ color: "var(--text)" }}>I3</span> — Close in Range: (close − open) / (high − open) · 1.0 = at high, 0 = at open</span>
            <span><span style={{ color: "var(--text)" }}>I4</span> — 15-day trading value history + today (highlighted) · yellow if &gt;1.5× avg</span>
            <span><span style={{ color: "var(--text)" }}>I5</span> — all-time high (★ if new ATH today) + 52-week high price &amp; date</span>
            <span><span style={{ color: "var(--text)" }}>I6</span> — NASDAQ % change (shown in table footer)</span>
          </div>
        </div>
      </main>
    </div>
  );
}
