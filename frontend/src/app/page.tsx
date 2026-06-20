"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import CandidatesTable from "@/components/CandidatesTable";
import MarketBar from "@/components/MarketBar";
import RefreshButton from "@/components/RefreshButton";
import { fetchLast, fetchRefresh } from "@/lib/api";
import type { DashboardData } from "@/types/dashboard";

// Auto-refresh window: every 2 min from 3:40–4:00 PM ET on weekdays. Gives a
// "live, streaming" feel into the close without ever blanking the screen.
const WINDOW_START_MIN = 15 * 60 + 40; // 15:40 ET
const WINDOW_END_MIN = 16 * 60; // 16:00 ET
const POLL_INTERVAL_MS = 2 * 60 * 1000; // 2 minutes
const TICK_MS = 20 * 1000; // how often we check the clock

/** Minutes-since-midnight and weekday in America/New_York, regardless of viewer TZ. */
function nowET(): { minutes: number; weekday: number } {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    hour: "2-digit",
    minute: "2-digit",
    weekday: "short",
    hour12: false,
  }).formatToParts(new Date());
  const hour = Number(parts.find((p) => p.type === "hour")?.value ?? "0");
  const minute = Number(parts.find((p) => p.type === "minute")?.value ?? "0");
  const wd = parts.find((p) => p.type === "weekday")?.value ?? "";
  const weekday = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].indexOf(wd);
  return { minutes: hour * 60 + minute, weekday };
}

function inAutoWindow(): boolean {
  const { minutes, weekday } = nowET();
  const isWeekday = weekday >= 1 && weekday <= 5;
  return isWeekday && minutes >= WINDOW_START_MIN && minutes <= WINDOW_END_MIN;
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [debug, setDebug] = useState(false);

  // Refs so the polling interval reads live values without re-subscribing.
  const refreshingRef = useRef(false);
  const hasDataRef = useRef(false);
  const lastStartRef = useRef(0);
  useEffect(() => { refreshingRef.current = refreshing; }, [refreshing]);
  useEffect(() => { hasDataRef.current = data !== null; }, [data]);

  // Core refresh. Background refreshes keep the current table on screen and only
  // swap in new rows when they arrive — no blank flash, just a live indicator.
  const runRefresh = useCallback(async () => {
    if (refreshingRef.current) return; // never overlap requests
    refreshingRef.current = true;
    lastStartRef.current = Date.now();
    setRefreshing(true);
    setError(null);
    try {
      const result = await fetchRefresh();
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      refreshingRef.current = false;
      setRefreshing(false);
    }
  }, []);

  // On open: show the last persisted snapshot immediately (survives cold starts),
  // then kick a fresh pull in the background if we have nothing yet.
  useEffect(() => {
    let cancelled = false;
    fetchLast()
      .then((d) => {
        if (cancelled) return;
        if (d) {
          setData(d);
          hasDataRef.current = true;
        } else {
          // Nothing cached anywhere → fetch so she never lands on a blank screen.
          runRefresh();
        }
      })
      .catch(() => { if (!cancelled) runRefresh(); });
    return () => { cancelled = true; };
  }, [runRefresh]);

  // Auto-poll during the closing window. Checks the clock every 20s and fires a
  // background refresh at most once per 2 min while in-window.
  useEffect(() => {
    const id = setInterval(() => {
      if (!inAutoWindow()) return;
      if (refreshingRef.current) return;
      if (Date.now() - lastStartRef.current < POLL_INTERVAL_MS) return;
      runRefresh();
    }, TICK_MS);
    return () => clearInterval(id);
  }, [runRefresh]);

  const emptyNasdaq = { rt_level: 0, open_level: 0, prev_close: 0, from_open_pct: 0, from_prev_close_pct: 0, error: null };

  // Big "fetching…" banner only on the very first load (no data yet). Once data
  // is on screen, refreshes are silent + in-place via the live indicator.
  const showInitialLoading = refreshing && data === null;

  return (
    <div className="min-h-screen flex flex-col" style={{ background: "var(--bg)" }}>
      {/* Header */}
      <header
        className="flex items-center justify-between px-6 py-5 border-b"
        style={{ background: "var(--surface)", borderColor: "var(--border)" }}
      >
        <div>
          <h1 className="text-xl font-semibold tracking-wide" style={{ color: "var(--text-bright)" }}>
            SFM
          </h1>
          <p className="text-sm mt-0.5" style={{ color: "var(--muted)" }}>
            Top 10 most active · 3:59 PM EST
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setDebug((d) => !d)}
            className={`px-3 py-2 rounded text-sm font-medium border transition-colors ${
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
      />

      {/* Main content */}
      <main className="flex-1 p-5 space-y-4">
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

        {/* Indicator legend — subdued, not competing for attention */}
        <div
          className="rounded p-4 text-sm space-y-1"
          style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
        >
          <p className="font-medium mb-2" style={{ color: "var(--muted)" }}>Indicator Reference</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-1" style={{ color: "var(--muted)" }}>
            <span><span style={{ color: "var(--text)" }}>I1</span> — (RT price − open) / open</span>
            <span><span style={{ color: "var(--text)" }}>I2</span> — (RT price − prev close) / prev close</span>
            <span><span style={{ color: "var(--text)" }}>I3</span> — (RT price − open) / (today high − open) · 1.0 = at day high, 0 = at open</span>
            <span><span style={{ color: "var(--text)" }}>I4</span> — bar chart: 15-day trading value history + today (highlighted) · yellow if &gt;1.5× avg</span>
            <span><span style={{ color: "var(--text)" }}>I5</span> — all-time high (★ if new ATH today) + 52-week high price &amp; date</span>
            <span><span style={{ color: "var(--text)" }}>I6</span> — NASDAQ % change (shown in table footer)</span>
          </div>
        </div>
      </main>
    </div>
  );
}
