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

  useEffect(() => {
    fetchLast()
      .then((d) => { if (d) setData(d); })
      .catch(() => {});
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
      <main className="flex-1 p-5 space-y-4">
        {error && (
          <div
            className="px-4 py-3 rounded text-sm"
            style={{ background: "#3a1a1a", border: "1px solid #5c2020", color: "#f0a0a0" }}
          >
            <strong>Error:</strong> {error}
            {!loading && (
              <span className="ml-2" style={{ color: "#d08080" }}>Previous data shown below.</span>
            )}
          </div>
        )}

        {loading && (
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
