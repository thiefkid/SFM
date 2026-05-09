"use client";

import type { NasdaqResult } from "@/types/dashboard";

function Pct({ value, label }: { value: number; label: string }) {
  const sign = value >= 0 ? "+" : "";
  const color = value >= 0 ? "text-green-400" : "text-red-400";
  return (
    <span className="flex items-center gap-1">
      <span className="text-slate-500 text-xs">{label}</span>
      <span className={`font-semibold ${color}`}>
        {sign}{(value * 100).toFixed(2)}%
      </span>
    </span>
  );
}

interface Props {
  nasdaq: NasdaqResult;
  refreshedAt: string | null;
  debug?: boolean;
}

export default function MarketBar({ nasdaq, refreshedAt, debug = false }: Props) {
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
      className="flex flex-wrap items-center gap-4 px-6 py-3 text-sm border-b"
      style={{ background: "var(--surface)", borderColor: "var(--border)" }}
    >
      {/* NASDAQ level */}
      <div className="flex items-center gap-2">
        <span className="text-slate-400 font-medium">NASDAQ</span>
        <span className="font-bold text-white text-base">
          {nasdaq.rt_level > 0 ? nasdaq.rt_level.toLocaleString() : "—"}
        </span>
      </div>

      <span className="text-slate-600">|</span>

      <div className="flex flex-col gap-0.5">
        <Pct value={nasdaq.from_open_pct} label="from open" />
        {debug && nasdaq.open_level > 0 && (
          <span className="text-amber-400/70 font-mono" style={{ fontSize: 10 }}>
            ({nasdaq.rt_level.toFixed(3)} − {nasdaq.open_level.toFixed(3)}) / {nasdaq.open_level.toFixed(3)}
          </span>
        )}
      </div>
      <div className="flex flex-col gap-0.5">
        <Pct value={nasdaq.from_prev_close_pct} label="from prev close" />
        {debug && nasdaq.prev_close > 0 && (
          <span className="text-amber-400/70 font-mono" style={{ fontSize: 10 }}>
            ({nasdaq.rt_level.toFixed(3)} − {nasdaq.prev_close.toFixed(3)}) / {nasdaq.prev_close.toFixed(3)}
          </span>
        )}
      </div>

      {nasdaq.error && (
        <span className="text-amber-400 text-xs">⚠ NASDAQ: {nasdaq.error}</span>
      )}

      {/* Spacer */}
      <div className="flex-1" />

      {time && (
        <span className="text-slate-500 text-xs">
          Last refreshed: <span className="text-slate-300">{time} ET</span>
        </span>
      )}
    </div>
  );
}
