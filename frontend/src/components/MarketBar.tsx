"use client";

import { useEffect, useRef, useState } from "react";
import type { MarketSession, NasdaqResult } from "@/types/dashboard";

function relativeAgo(ms: number): string {
  if (ms < 0) ms = 0;
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function Pct({ value, label }: { value: number; label: string }) {
  const sign = value >= 0 ? "+" : "";
  const color = value >= 0 ? "var(--green)" : "var(--red)";
  return (
    <span className="flex items-center gap-2">
      <span className="text-sm" style={{ color: "var(--muted)" }}>{label}</span>
      <span className="font-semibold text-base tabular-nums" style={{ color }}>
        {sign}{(value * 100).toFixed(2)}%
      </span>
    </span>
  );
}

function sessionDot(session: MarketSession["session"]): { color: string; pulse: boolean } {
  switch (session) {
    case "regular":
      return { color: "var(--green)", pulse: true };
    case "pre_market":
      return { color: "var(--gold)", pulse: true };
    case "after_hours":
      return { color: "var(--blue)", pulse: true };
    default:
      return { color: "var(--muted)", pulse: false };
  }
}

interface Props {
  nasdaq: NasdaqResult;
  refreshedAt: string | null;
  serverTime?: string | null;
  refreshing?: boolean;
  marketSession?: MarketSession | null;
}

export default function MarketBar({ nasdaq, refreshedAt, serverTime, refreshing = false, marketSession }: Props) {
  // Tick every second so the "ago" stays live.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  // Anchor "ago" on the backend clock: skew = how far the client clock leads the
  // backend's reported server_time. backendNow ≈ Date.now() - skew. This keeps the
  // freshness reading correct even if the user's device clock is wrong.
  const skewRef = useRef(0);
  useEffect(() => {
    if (serverTime) {
      const st = new Date(serverTime).getTime();
      if (!isNaN(st)) skewRef.current = Date.now() - st;
    }
  }, [serverTime]);

  const refreshedMs = refreshedAt ? new Date(refreshedAt).getTime() : NaN;
  const time = refreshedAt
    ? new Date(refreshedAt).toLocaleString("en-US", {
        timeZone: "America/New_York",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })
    : null;
  const ago = !isNaN(refreshedMs) ? relativeAgo(now - skewRef.current - refreshedMs) : null;

  return (
    <div
      className="flex flex-wrap items-center gap-x-5 gap-y-2 px-4 sm:px-6 py-3 border-b"
      style={{ background: "var(--surface)", borderColor: "var(--border)" }}
    >
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium" style={{ color: "var(--muted)" }}>NASDAQ</span>
        <span className="font-bold text-lg tabular-nums" style={{ color: "var(--text-bright)" }}>
          {nasdaq.rt_level > 0 ? nasdaq.rt_level.toLocaleString(undefined, { maximumFractionDigits: 0 }) : "—"}
        </span>
      </div>

      {marketSession && (() => {
        const dot = sessionDot(marketSession.session);
        return (
          <div className="flex items-center gap-2">
            <span className="relative flex h-2 w-2 shrink-0">
              {dot.pulse && (
                <span
                  className="absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping"
                  style={{ background: dot.color }}
                />
              )}
              <span
                className="relative inline-flex h-2 w-2 rounded-full"
                style={{ background: dot.color }}
              />
            </span>
            <span className="text-sm font-medium whitespace-nowrap" style={{ color: dot.color }}>
              {marketSession.label}
            </span>
          </div>
        );
      })()}

      <span style={{ color: "var(--border)" }}>|</span>

      <Pct value={nasdaq.from_open_pct} label="from open" />
      <Pct value={nasdaq.from_prev_close_pct} label="prev close" />

      {nasdaq.error && (
        <span className="text-sm" style={{ color: "var(--gold)" }}>NASDAQ: {nasdaq.error}</span>
      )}

      <div className="flex-1" />

      {refreshing && (
        <span className="flex items-center gap-2 text-sm" style={{ color: "var(--green)" }}>
          <span className="relative flex h-2.5 w-2.5">
            <span
              className="absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping"
              style={{ background: "var(--green)" }}
            />
            <span
              className="relative inline-flex h-2.5 w-2.5 rounded-full"
              style={{ background: "var(--green)" }}
            />
          </span>
          Updating…
        </span>
      )}

      {time && (
        <span className="text-sm" style={{ color: "var(--muted)" }}>
          Refreshed <span style={{ color: "var(--text)" }}>{time} ET</span>
          {ago && <span className="ml-1.5" style={{ color: "var(--muted)" }}>· {ago}</span>}
        </span>
      )}
    </div>
  );
}
