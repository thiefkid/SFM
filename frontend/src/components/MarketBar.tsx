"use client";

import type { NasdaqResult } from "@/types/dashboard";

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

interface Props {
  nasdaq: NasdaqResult;
  refreshedAt: string | null;
  refreshing?: boolean;
  debug?: boolean;
}

export default function MarketBar({ nasdaq, refreshedAt, refreshing = false, debug = false }: Props) {
  const time = refreshedAt
    ? new Date(refreshedAt).toLocaleTimeString("en-US", {
        timeZone: "America/New_York",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })
    : null;

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

      <span style={{ color: "var(--border)" }}>|</span>

      <div className="flex flex-col gap-0.5">
        <Pct value={nasdaq.from_open_pct} label="from open" />
        {debug && nasdaq.open_level > 0 && (
          <span className="font-mono text-amber-400/70" style={{ fontSize: 11 }}>
            ({nasdaq.rt_level.toFixed(2)} - {nasdaq.open_level.toFixed(2)}) / {nasdaq.open_level.toFixed(2)}
          </span>
        )}
      </div>
      <div className="flex flex-col gap-0.5">
        <Pct value={nasdaq.from_prev_close_pct} label="prev close" />
        {debug && nasdaq.prev_close > 0 && (
          <span className="font-mono text-amber-400/70" style={{ fontSize: 11 }}>
            ({nasdaq.rt_level.toFixed(2)} - {nasdaq.prev_close.toFixed(2)}) / {nasdaq.prev_close.toFixed(2)}
          </span>
        )}
      </div>

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
        </span>
      )}
    </div>
  );
}
