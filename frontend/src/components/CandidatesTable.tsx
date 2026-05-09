"use client";

import type { StockResult } from "@/types/dashboard";

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

function fmtPct(value: number | null): string {
  if (value === null) return "—";
  const sign = value >= 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(2)}%`;
}

function fmtValue(value: number): string {
  if (value === 0) return "—";
  if (value >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(2)}B`;
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  return `$${value.toLocaleString()}`;
}

function fmtPrice(value: number): string {
  if (value === 0) return "—";
  return `$${value.toFixed(2)}`;
}

// ---------------------------------------------------------------------------
// Color helpers
// ---------------------------------------------------------------------------

function pctColor(value: number | null): string {
  if (value === null) return "text-slate-500";
  if (value > 0) return "text-green-400";
  if (value < 0) return "text-red-400";
  return "text-slate-400";
}

function i3Color(value: number | null): string {
  if (value === null) return "text-slate-500";
  if (value >= 0.8) return "text-green-400";
  if (value >= 0.4) return "text-yellow-400";
  return "text-red-400";
}

// ---------------------------------------------------------------------------
// Cell components
// ---------------------------------------------------------------------------

function I3Cell({ value }: { value: number | null }) {
  if (value === null) return <span className="text-slate-500">—</span>;
  return (
    <div className="flex flex-col gap-0.5">
      <span className={i3Color(value)}>{fmtPct(value)}</span>
      {/* Mini bar */}
      <div className="w-full h-1 rounded-full bg-slate-700 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${
            value >= 0.8 ? "bg-green-400" : value >= 0.4 ? "bg-yellow-400" : "bg-red-400"
          }`}
          style={{ width: `${Math.max(0, Math.min(100, value * 100))}%` }}
        />
      </div>
    </div>
  );
}

function I4Cell({ today_value, past_values, avg, ratio, day_count }: StockResult["i4"]) {
  // All bars: past days + today. Find max for scaling.
  const allValues = [...past_values, today_value];
  const maxVal = Math.max(...allValues, 1);

  return (
    <div className="flex flex-col gap-1" style={{ minWidth: 180 }}>
      {/* Bar chart */}
      <div className="flex items-end gap-px h-10">
        {past_values.map((v, i) => {
          const heightPct = (v / maxVal) * 100;
          return (
            <div
              key={i}
              className="flex-1 rounded-sm bg-slate-600 hover:bg-slate-400 transition-colors"
              style={{ height: `${Math.max(4, heightPct)}%` }}
              title={fmtValue(v)}
            />
          );
        })}
        {/* Today — highlighted */}
        <div
          className={`flex-1 rounded-sm transition-colors ${
            ratio !== null && ratio >= 1.5
              ? "bg-yellow-400"
              : ratio !== null && ratio >= 1.0
              ? "bg-blue-400"
              : "bg-slate-400"
          }`}
          style={{ height: `${Math.max(4, (today_value / maxVal) * 100)}%` }}
          title={`Today: ${fmtValue(today_value)}`}
        />
      </div>
      {/* Labels */}
      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-500">{day_count}d avg: {fmtValue(avg)}</span>
        <span className={ratio !== null && ratio >= 1.5 ? "text-yellow-300 font-bold" : "text-slate-300"}>
          {ratio !== null ? `${ratio.toFixed(2)}×` : "—"}
        </span>
      </div>
      <span className="text-slate-600 text-xs">today: {fmtValue(today_value)}</span>
    </div>
  );
}

function fmtDateShort(isoDate: string | null): string {
  if (!isoDate) return "—";
  return new Date(isoDate).toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric",
  });
}

function I5Cell({ is_ath, ath_price, ath_date, days_since_ath, year_high, year_high_date }: StockResult["i5"]) {
  return (
    <div className="flex flex-col gap-1 text-xs">
      {/* ATH row */}
      {is_ath ? (
        <span
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded font-bold w-fit"
          style={{ background: "#78350f", color: "#fcd34d" }}
        >
          ★ ATH TODAY
        </span>
      ) : (
        <div className="flex flex-col">
          <span className="text-slate-400 uppercase tracking-wider" style={{ fontSize: 10 }}>ATH</span>
          <span className="text-slate-300">
            {ath_price ? `$${ath_price.toFixed(2)}` : "N/A"}
          </span>
          {ath_date && (
            <span className="text-slate-500">
              {fmtDateShort(ath_date)}
              {days_since_ath !== null && (
                <span className="text-slate-600"> ({days_since_ath}d ago)</span>
              )}
            </span>
          )}
        </div>
      )}

      {/* Divider */}
      <div style={{ borderTop: "1px solid #2a2d3a" }} />

      {/* 52-week high row */}
      <div className="flex flex-col">
        <span className="text-slate-400 uppercase tracking-wider" style={{ fontSize: 10 }}>52W High</span>
        <span className="text-slate-300">
          {year_high ? `$${year_high.toFixed(2)}` : "N/A"}
        </span>
        {year_high_date && (
          <span className="text-slate-500">{fmtDateShort(year_high_date)}</span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Table
// ---------------------------------------------------------------------------

const TH = ({ children, cls = "" }: { children: React.ReactNode; cls?: string }) => (
  <th
    className={`px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-slate-500 whitespace-nowrap ${cls}`}
    style={{ borderBottom: "1px solid var(--border)" }}
  >
    {children}
  </th>
);

const TD = ({ children, cls = "" }: { children: React.ReactNode; cls?: string }) => (
  <td
    className={`px-3 py-3 text-sm ${cls}`}
    style={{ borderBottom: "1px solid #1e2030" }}
  >
    {children}
  </td>
);

function DebugFormula({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-1 font-mono text-amber-400/70 leading-tight" style={{ fontSize: 10 }}>
      {children}
    </div>
  );
}

interface Props {
  stocks: StockResult[];
  debug?: boolean;
}

export default function CandidatesTable({ stocks, debug = false }: Props) {
  if (stocks.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-slate-500">
        No data — click Refresh Data to load candidates
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg" style={{ border: "1px solid var(--border)" }}>
      <table className="w-full border-collapse text-left">
        <thead style={{ background: "var(--surface)" }}>
          <tr>
            <TH>#</TH>
            <TH>Symbol</TH>
            <TH>Price</TH>
            <TH cls="min-w-[110px]">
              I1 — From Open
            </TH>
            <TH cls="min-w-[120px]">
              I2 — Day Change
            </TH>
            <TH cls="min-w-[130px]">
              I3 — Range Pos.
            </TH>
            <TH cls="min-w-[200px]">
              I4 — Trading Value (15d)
            </TH>
            <TH cls="min-w-[180px]">
              I5 — ATH / 52W High
            </TH>
          </tr>
        </thead>
        <tbody>
          {stocks.map((stock) => (
            <tr
              key={stock.symbol}
              className="transition-colors hover:bg-white/[0.02]"
            >
              <TD>
                <span className="text-slate-600 text-xs">{stock.rank}</span>
              </TD>

              <TD>
                <div className="flex flex-col">
                  <span className="font-bold text-white tracking-wide">{stock.symbol}</span>
                  {stock.scrape_error && (
                    <span className="text-amber-400 text-xs" title={stock.scrape_error}>
                      ⚠ partial
                    </span>
                  )}
                </div>
              </TD>

              <TD>
                <span className="text-white font-medium">{fmtPrice(stock.rt_price)}</span>
              </TD>

              {/* I1 */}
              <TD>
                <span className={`font-semibold ${pctColor(stock.i1)}`}>
                  {fmtPct(stock.i1)}
                </span>
                {debug && stock.open_price > 0 && (
                  <DebugFormula>
                    ({stock.rt_price.toFixed(3)} − {stock.open_price.toFixed(3)}) / {stock.open_price.toFixed(3)}
                  </DebugFormula>
                )}
              </TD>

              {/* I2 */}
              <TD>
                <span className={`font-semibold ${pctColor(stock.i2)}`}>
                  {fmtPct(stock.i2)}
                </span>
                {debug && stock.prev_close > 0 && (
                  <DebugFormula>
                    ({stock.rt_price.toFixed(3)} − {stock.prev_close.toFixed(3)}) / {stock.prev_close.toFixed(3)}
                  </DebugFormula>
                )}
              </TD>

              {/* I3 */}
              <TD>
                <I3Cell value={stock.i3} />
                {debug && stock.open_price > 0 && stock.today_high > stock.open_price && (
                  <DebugFormula>
                    ({stock.rt_price.toFixed(3)} − {stock.open_price.toFixed(3)}) / ({stock.today_high.toFixed(3)} − {stock.open_price.toFixed(3)})
                  </DebugFormula>
                )}
              </TD>

              {/* I4 */}
              <TD>
                <I4Cell {...stock.i4} />
              </TD>

              {/* I5 */}
              <TD>
                <I5Cell {...stock.i5} />
              </TD>
            </tr>
          ))}
        </tbody>
      </table>

      {/* I6 footer — NASDAQ context applies to all stocks equally */}
      {stocks.length > 0 && (
        <div
          className="px-4 py-2 text-xs text-slate-500 flex flex-wrap gap-x-6 gap-y-1"
          style={{ borderTop: "1px solid var(--border)", background: "var(--surface)" }}
        >
          <div className="flex flex-col gap-0.5">
            <span>
              I6 — NASDAQ from open:{" "}
              <span className={pctColor(stocks[0].i6.nasdaq_from_open_pct)}>
                {fmtPct(stocks[0].i6.nasdaq_from_open_pct)}
              </span>
            </span>
          </div>
          <div className="flex flex-col gap-0.5">
            <span>
              NASDAQ from prev close:{" "}
              <span className={pctColor(stocks[0].i6.nasdaq_from_prev_close_pct)}>
                {fmtPct(stocks[0].i6.nasdaq_from_prev_close_pct)}
              </span>
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
