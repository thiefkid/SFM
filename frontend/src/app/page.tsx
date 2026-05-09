"use client";

import { useCallback, useEffect, useState } from "react";

import CandidatesTable from "@/components/CandidatesTable";
import MarketBar from "@/components/MarketBar";
import RefreshButton from "@/components/RefreshButton";
import { fetchLast, fetchRefresh } from "@/lib/api";
import type { DashboardData } from "@/types/dashboard";

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [debug, setDebug] = useState(false);

  // Load last result on mount
  useEffect(() => {
    fetchLast()
      .then((d) => { if (d) setData(d); })
      .catch(() => {/* no previous data — fine */});
  }, []);

  const handleRefresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchRefresh();
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, []);

  const emptyNasdaq = { rt_level: 0, open_level: 0, prev_close: 0, from_open_pct: 0, from_prev_close_pct: 0, error: null };

  return (
    <div className="min-h-screen flex flex-col" style={{ background: "var(--bg)" }}>
      {/* Header */}
      <header
        className="flex items-center justify-between px-6 py-4 border-b"
        style={{ background: "var(--surface)", borderColor: "var(--border)" }}
      >
        <div>
          <h1 className="text-lg font-bold text-white tracking-wide">
            SFM — Stock Pick Dashboard
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Top 10 most active US stocks · Futu indicators · 3:59 PM EST
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setDebug((d) => !d)}
            className={`px-3 py-1.5 rounded text-xs font-medium border transition-colors ${
              debug
                ? "bg-amber-500/20 border-amber-500/50 text-amber-300"
                : "bg-transparent border-slate-600 text-slate-500 hover:text-slate-300 hover:border-slate-400"
            }`}
          >
            {debug ? "Debug ON" : "Debug"}
          </button>
          <RefreshButton loading={loading} onClick={handleRefresh} />
        </div>
      </header>

      {/* NASDAQ bar */}
      <MarketBar
        nasdaq={data?.nasdaq ?? emptyNasdaq}
        refreshedAt={data?.refreshed_at ?? null}
        debug={debug}
      />

      {/* Main content */}
      <main className="flex-1 p-6 space-y-4">
        {/* Error banner */}
        {error && (
          <div
            className="px-4 py-3 rounded text-sm"
            style={{ background: "#450a0a", border: "1px solid #7f1d1d", color: "#fca5a5" }}
          >
            <strong>Error:</strong> {error}
            {loading === false && (
              <span className="text-red-400 ml-2">Previous data shown below.</span>
            )}
          </div>
        )}

        {/* Loading hint */}
        {loading && (
          <div
            className="px-4 py-3 rounded text-sm text-blue-300"
            style={{ background: "#172554", border: "1px solid #1d4ed8" }}
          >
            Scraping Futu for top 10 candidates + fetching historical data…
            this takes ~20–40 seconds.
          </div>
        )}

        {/* Table */}
        <CandidatesTable stocks={data?.stocks ?? []} debug={debug} />

        {/* Indicator legend */}
        <div
          className="rounded p-4 text-xs space-y-1"
          style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
        >
          <p className="text-slate-400 font-medium mb-2">Indicator Reference</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-1 text-slate-500">
            <span><span className="text-slate-300">I1</span> — (RT price − open) / open</span>
            <span><span className="text-slate-300">I2</span> — (RT price − prev close) / prev close</span>
            <span><span className="text-slate-300">I3</span> — (RT price − open) / (today high − open) · 1.0 = at day high, 0 = at open</span>
            <span><span className="text-slate-300">I4</span> — bar chart: 15-day trading value history + today (highlighted) · yellow if &gt;1.5× avg</span>
            <span><span className="text-slate-300">I5</span> — all-time high (★ if new ATH today) + 52-week high price &amp; date</span>
            <span><span className="text-slate-300">I6</span> — NASDAQ % change (shown in table footer)</span>
          </div>
        </div>
      </main>
    </div>
  );
}
