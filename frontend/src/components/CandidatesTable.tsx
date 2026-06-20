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
// Color helpers — softer for dark-room viewing
// ---------------------------------------------------------------------------

function pctColor(value: number | null): string {
  if (value === null) return "var(--muted)";
  if (value > 0) return "var(--green)";
  if (value < 0) return "var(--red)";
  return "var(--text)";
}

function i3Color(value: number | null): string {
  if (value === null) return "var(--muted)";
  if (value >= 0.8) return "var(--green)";
  if (value >= 0.4) return "var(--gold)";
  return "var(--red)";
}

function i3BarColor(value: number): string {
  if (value >= 0.8) return "var(--green)";
  if (value >= 0.4) return "var(--gold)";
  return "var(--red)";
}

// ---------------------------------------------------------------------------
// Cell components
// ---------------------------------------------------------------------------

function I3Cell({ value }: { value: number | null }) {
  if (value === null) return <span style={{ color: "var(--muted)" }}>—</span>;
  return (
    <div className="flex flex-col gap-1">
      <span className="tabular-nums font-semibold" style={{ color: i3Color(value) }}>
        {fmtPct(value)}
      </span>
      <div className="w-full h-1.5 rounded-full overflow-hidden" style={{ background: "var(--border)" }}>
        <div
          className="h-full rounded-full transition-all"
          style={{
            width: `${Math.max(0, Math.min(100, value * 100))}%`,
            background: i3BarColor(value),
          }}
        />
      </div>
    </div>
  );
}

function I4Cell({ today_value, past_values, avg, ratio, day_count }: StockResult["i4"]) {
  const allValues = [...past_values, today_value];
  const maxVal = Math.max(...allValues, 1);

  const todayColor =
    ratio !== null && ratio >= 1.5
      ? "var(--gold)"
      : ratio !== null && ratio >= 1.0
      ? "var(--blue)"
      : "var(--muted)";

  return (
    <div className="flex flex-col gap-1.5" style={{ minWidth: 200 }}>
      <div className="flex items-end gap-px" style={{ height: 36 }}>
        {past_values.map((v, i) => {
          const heightPct = (v / maxVal) * 100;
          return (
            <div
              key={i}
              className="flex-1 rounded-sm transition-colors"
              style={{
                height: `${Math.max(4, heightPct)}%`,
                background: "var(--muted)",
                opacity: 0.5,
              }}
              title={fmtValue(v)}
            />
          );
        })}
        <div
          className="flex-1 rounded-sm"
          style={{
            height: `${Math.max(4, (today_value / maxVal) * 100)}%`,
            background: todayColor,
          }}
          title={`Today: ${fmtValue(today_value)}`}
        />
      </div>
      <div className="flex items-center justify-between text-sm">
        <span style={{ color: "var(--muted)" }}>{day_count}d avg: {fmtValue(avg)}</span>
        <span
          className="tabular-nums font-semibold"
          style={{ color: ratio !== null && ratio >= 1.5 ? "var(--gold)" : "var(--text)" }}
        >
          {ratio !== null ? `${ratio.toFixed(2)}x` : "—"}
        </span>
      </div>
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
    <div className="flex flex-col gap-1.5 text-sm">
      {is_ath ? (
        <span
          className="inline-flex items-center gap-1 px-3 py-1 rounded font-bold w-fit"
          style={{ background: "#3a2a10", color: "var(--gold)", fontSize: 14 }}
        >
          ATH TODAY
        </span>
      ) : (
        <div className="flex flex-col gap-0.5">
          <span className="uppercase tracking-wider" style={{ color: "var(--muted)", fontSize: 12 }}>ATH</span>
          <span className="tabular-nums" style={{ color: "var(--text)" }}>
            {ath_price ? `$${ath_price.toFixed(2)}` : "N/A"}
          </span>
          {ath_date && (
            <span style={{ color: "var(--muted)", fontSize: 13 }}>
              {fmtDateShort(ath_date)}
              {days_since_ath !== null && (
                <span style={{ opacity: 0.6 }}> ({days_since_ath}d)</span>
              )}
            </span>
          )}
        </div>
      )}

      <div style={{ borderTop: "1px solid var(--border)" }} />

      <div className="flex flex-col gap-0.5">
        <span className="uppercase tracking-wider" style={{ color: "var(--muted)", fontSize: 12 }}>52W High</span>
        <span className="tabular-nums" style={{ color: "var(--text)" }}>
          {year_high ? `$${year_high.toFixed(2)}` : "N/A"}
        </span>
        {year_high_date && (
          <span style={{ color: "var(--muted)", fontSize: 13 }}>{fmtDateShort(year_high_date)}</span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Table
// ---------------------------------------------------------------------------

const TH = ({ children, style: extraStyle }: { children: React.ReactNode; style?: React.CSSProperties }) => (
  <th
    className="px-4 py-3 text-left font-medium uppercase tracking-wider whitespace-nowrap"
    style={{
      borderBottom: "1px solid var(--border)",
      color: "var(--muted)",
      fontSize: 13,
      ...extraStyle,
    }}
  >
    {children}
  </th>
);

const TD = ({ children, style: extraStyle }: { children: React.ReactNode; style?: React.CSSProperties }) => (
  <td
    className="px-4 py-4"
    style={{
      borderBottom: "1px solid var(--border)",
      fontSize: 15,
      ...extraStyle,
    }}
  >
    {children}
  </td>
);

function DebugFormula({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-1 font-mono text-amber-400/70 leading-tight" style={{ fontSize: 11 }}>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Mobile card (shown < md, where a 8-column table would force horizontal scroll)
// ---------------------------------------------------------------------------

function CardStat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1 min-w-0">
      <span className="uppercase tracking-wider" style={{ color: "var(--muted)", fontSize: 11 }}>
        {label}
      </span>
      {children}
    </div>
  );
}

function StockCard({ stock, debug }: { stock: StockResult; debug: boolean }) {
  return (
    <div
      className="rounded-lg p-4 space-y-4"
      style={{ border: "1px solid var(--border)", background: "var(--surface)" }}
    >
      {/* Symbol + price */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-baseline gap-2.5 min-w-0">
          <span className="tabular-nums shrink-0" style={{ color: "var(--muted)", fontSize: 14 }}>
            #{stock.rank}
          </span>
          <span className="font-bold tracking-wide truncate" style={{ color: "var(--text-bright)", fontSize: 22 }}>
            {stock.symbol}
          </span>
          {stock.scrape_error && (
            <span className="shrink-0" style={{ color: "var(--gold)", fontSize: 12 }} title={stock.scrape_error}>
              partial
            </span>
          )}
        </div>
        <span className="tabular-nums font-semibold shrink-0" style={{ color: "var(--text-bright)", fontSize: 22 }}>
          {fmtPrice(stock.rt_price)}
        </span>
      </div>

      {/* I1 / I2 / I3 */}
      <div className="grid grid-cols-3 gap-3">
        <CardStat label="I1 · Open">
          <span className="tabular-nums font-semibold" style={{ color: pctColor(stock.i1), fontSize: 15 }}>
            {fmtPct(stock.i1)}
          </span>
        </CardStat>
        <CardStat label="I2 · Chg">
          <span className="tabular-nums font-semibold" style={{ color: pctColor(stock.i2), fontSize: 15 }}>
            {fmtPct(stock.i2)}
          </span>
        </CardStat>
        <CardStat label="I3 · Range">
          <I3Cell value={stock.i3} />
        </CardStat>
      </div>

      {debug && (
        <DebugFormula>
          {stock.open_price > 0 && (
            <div>I1=({stock.rt_price.toFixed(2)}−{stock.open_price.toFixed(2)})/{stock.open_price.toFixed(2)}</div>
          )}
          {stock.prev_close > 0 && (
            <div>I2=({stock.rt_price.toFixed(2)}−{stock.prev_close.toFixed(2)})/{stock.prev_close.toFixed(2)}</div>
          )}
          {stock.open_price > 0 && stock.today_high > stock.open_price && (
            <div>I3=({stock.rt_price.toFixed(2)}−{stock.open_price.toFixed(2)})/({stock.today_high.toFixed(2)}−{stock.open_price.toFixed(2)})</div>
          )}
        </DebugFormula>
      )}

      {/* I4 */}
      <CardStat label="I4 · Volume (15d)">
        <I4Cell {...stock.i4} />
      </CardStat>

      {/* I5 */}
      <div className="pt-3" style={{ borderTop: "1px solid var(--border)" }}>
        <I5Cell {...stock.i5} />
      </div>
    </div>
  );
}

function I6Footer({ stock }: { stock: StockResult }) {
  return (
    <div
      className="rounded-lg px-4 py-3 flex flex-wrap gap-x-6 gap-y-1"
      style={{ border: "1px solid var(--border)", background: "var(--surface)", fontSize: 14 }}
    >
      <span style={{ color: "var(--muted)" }}>
        I6 — NASDAQ from open:{" "}
        <span className="tabular-nums font-semibold" style={{ color: pctColor(stock.i6.nasdaq_from_open_pct) }}>
          {fmtPct(stock.i6.nasdaq_from_open_pct)}
        </span>
      </span>
      <span style={{ color: "var(--muted)" }}>
        from prev close:{" "}
        <span className="tabular-nums font-semibold" style={{ color: pctColor(stock.i6.nasdaq_from_prev_close_pct) }}>
          {fmtPct(stock.i6.nasdaq_from_prev_close_pct)}
        </span>
      </span>
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
      <div
        className="flex items-center justify-center rounded-lg"
        style={{ height: 200, color: "var(--muted)", fontSize: 16, border: "1px solid var(--border)" }}
      >
        No data — tap Refresh to load
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Mobile: stacked cards (no horizontal scroll) */}
      <div className="md:hidden space-y-3">
        {stocks.map((stock) => (
          <StockCard key={stock.symbol} stock={stock} debug={debug} />
        ))}
      </div>

      {/* Desktop / tablet: full table */}
      <div className="hidden md:block overflow-x-auto rounded-lg" style={{ border: "1px solid var(--border)" }}>
        <table className="w-full border-collapse text-left">
          <thead style={{ background: "var(--surface)" }}>
            <tr>
              <TH>#</TH>
              <TH>Symbol</TH>
              <TH>Price</TH>
              <TH style={{ minWidth: 120 }}>I1 — Open</TH>
              <TH style={{ minWidth: 130 }}>I2 — Change</TH>
              <TH style={{ minWidth: 140 }}>I3 — Range</TH>
              <TH style={{ minWidth: 220 }}>I4 — Volume (15d)</TH>
              <TH style={{ minWidth: 190 }}>I5 — ATH / 52W</TH>
            </tr>
          </thead>
          <tbody>
            {stocks.map((stock) => (
              <tr
                key={stock.symbol}
                className="transition-colors"
                style={{ background: "transparent" }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(255,255,255,0.02)")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
              >
                <TD>
                  <span className="tabular-nums" style={{ color: "var(--muted)", fontSize: 14 }}>
                    {stock.rank}
                  </span>
                </TD>

                <TD>
                  <div className="flex flex-col">
                    <span className="font-bold tracking-wide" style={{ color: "var(--text-bright)", fontSize: 16 }}>
                      {stock.symbol}
                    </span>
                    {stock.scrape_error && (
                      <span style={{ color: "var(--gold)", fontSize: 13 }} title={stock.scrape_error}>
                        partial
                      </span>
                    )}
                  </div>
                </TD>

                <TD>
                  <span className="tabular-nums font-semibold" style={{ color: "var(--text-bright)", fontSize: 16 }}>
                    {fmtPrice(stock.rt_price)}
                  </span>
                </TD>

                {/* I1 */}
                <TD>
                  <span className="tabular-nums font-semibold" style={{ color: pctColor(stock.i1), fontSize: 15 }}>
                    {fmtPct(stock.i1)}
                  </span>
                  {debug && stock.open_price > 0 && (
                    <DebugFormula>
                      ({stock.rt_price.toFixed(2)} - {stock.open_price.toFixed(2)}) / {stock.open_price.toFixed(2)}
                    </DebugFormula>
                  )}
                </TD>

                {/* I2 */}
                <TD>
                  <span className="tabular-nums font-semibold" style={{ color: pctColor(stock.i2), fontSize: 15 }}>
                    {fmtPct(stock.i2)}
                  </span>
                  {debug && stock.prev_close > 0 && (
                    <DebugFormula>
                      ({stock.rt_price.toFixed(2)} - {stock.prev_close.toFixed(2)}) / {stock.prev_close.toFixed(2)}
                    </DebugFormula>
                  )}
                </TD>

                {/* I3 */}
                <TD>
                  <I3Cell value={stock.i3} />
                  {debug && stock.open_price > 0 && stock.today_high > stock.open_price && (
                    <DebugFormula>
                      ({stock.rt_price.toFixed(2)} - {stock.open_price.toFixed(2)}) / ({stock.today_high.toFixed(2)} - {stock.open_price.toFixed(2)})
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
      </div>

      {/* I6 footer — shared by both views */}
      <I6Footer stock={stocks[0]} />
    </div>
  );
}
