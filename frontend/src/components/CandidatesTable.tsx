"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import type { StockResult } from "@/types/dashboard";
import { fetchNews, type NewsArticle } from "@/lib/api";

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

function fmtMarketCap(value: number | null | undefined): string | null {
  if (value == null || value <= 0) return null;
  if (value >= 1_000_000_000_000) return `$${(value / 1_000_000_000_000).toFixed(2)}T`;
  if (value >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(1)}B`;
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(0)}M`;
  return `$${value.toLocaleString()}`;
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
// Formula builders (tap-to-reveal)
// ---------------------------------------------------------------------------

function i1Formula(s: StockResult): string | null {
  if (s.open_price <= 0) return null;
  return `(${s.rt_price.toFixed(2)} − ${s.open_price.toFixed(2)}) / ${s.open_price.toFixed(2)}`;
}

function i2Formula(s: StockResult): string | null {
  if (s.prev_close <= 0) return null;
  return `(${s.rt_price.toFixed(2)} − ${s.prev_close.toFixed(2)}) / ${s.prev_close.toFixed(2)}`;
}

function i3Formula(s: StockResult): string | null {
  if (s.open_price <= 0 || s.today_high <= s.open_price) return null;
  return `(${s.rt_price.toFixed(2)} − ${s.open_price.toFixed(2)}) / (${s.today_high.toFixed(2)} − ${s.open_price.toFixed(2)})`;
}

// ---------------------------------------------------------------------------
// Tappable indicator cells (tap value → shows formula)
// ---------------------------------------------------------------------------

function TappablePct({
  value,
  formula,
  colorFn = pctColor,
}: {
  value: number | null;
  formula: string | null;
  colorFn?: (v: number | null) => string;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div
      className="cursor-pointer select-none"
      onClick={() => formula && setExpanded((e) => !e)}
    >
      <span
        className="tabular-nums font-semibold"
        style={{ color: colorFn(value), fontSize: 15 }}
      >
        {fmtPct(value)}
      </span>
      {expanded && formula && (
        <div
          className="mt-1 font-mono leading-tight"
          style={{ fontSize: 11, color: "var(--gold)", opacity: 0.7 }}
        >
          {formula}
        </div>
      )}
    </div>
  );
}

function TappableI3({
  value,
  formula,
}: {
  value: number | null;
  formula: string | null;
}) {
  const [expanded, setExpanded] = useState(false);
  if (value === null) return <span style={{ color: "var(--muted)" }}>—</span>;
  return (
    <div
      className="flex flex-col gap-1 cursor-pointer select-none"
      onClick={() => formula && setExpanded((e) => !e)}
    >
      <span
        className="tabular-nums font-semibold"
        style={{ color: i3Color(value) }}
      >
        {fmtPct(value)}
      </span>
      <div
        className="w-full h-1.5 rounded-full overflow-hidden"
        style={{ background: "var(--border)" }}
      >
        <div
          className="h-full rounded-full transition-all"
          style={{
            width: `${Math.max(0, Math.min(100, value * 100))}%`,
            background: i3BarColor(value),
          }}
        />
      </div>
      {expanded && formula && (
        <div
          className="mt-0.5 font-mono leading-tight"
          style={{ fontSize: 11, color: "var(--gold)", opacity: 0.7 }}
        >
          {formula}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Cell components
// ---------------------------------------------------------------------------

function fmtTooltipDate(isoDate: string | null): string {
  if (!isoDate) return "—";
  const [y, m, d] = isoDate.split("-").map(Number);
  if (!y || !m || !d) return isoDate;
  return new Date(y, m - 1, d).toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

function I4Cell({
  today_value,
  past_values,
  avg,
  ratio,
  day_count,
  dates,
  today_date,
}: StockResult["i4"]) {
  const allValues = [...past_values, today_value];
  const maxVal = Math.max(...allValues, 1);
  const [activeBar, setActiveBar] = useState<number | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const todayColor =
    ratio !== null && ratio >= 1.5
      ? "var(--gold)"
      : ratio !== null && ratio >= 1.0
      ? "var(--blue)"
      : "var(--muted)";

  const todayIndex = past_values.length;

  const getTooltipText = useCallback(
    (index: number): string => {
      if (index === todayIndex) {
        return `${today_date ? fmtTooltipDate(today_date) : "Today"} (today) · ${fmtValue(today_value)}`;
      }
      return `${fmtTooltipDate(dates[index] ?? null)} · ${fmtValue(past_values[index])}`;
    },
    [todayIndex, today_date, today_value, dates, past_values]
  );

  useEffect(() => {
    if (activeBar === null) return;
    const handleOutside = (e: TouchEvent | MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setActiveBar(null);
      }
    };
    document.addEventListener("touchstart", handleOutside);
    document.addEventListener("mousedown", handleOutside);
    return () => {
      document.removeEventListener("touchstart", handleOutside);
      document.removeEventListener("mousedown", handleOutside);
    };
  }, [activeBar]);

  return (
    <div
      className="flex flex-col gap-1.5"
      style={{ minWidth: 200 }}
      ref={containerRef}
    >
      <div
        className="relative flex items-end gap-px"
        style={{ height: 36 }}
      >
        {past_values.map((v, i) => {
          const heightPct = (v / maxVal) * 100;
          return (
            <div
              key={i}
              className="flex-1 rounded-sm transition-colors cursor-pointer"
              style={{
                height: `${Math.max(4, heightPct)}%`,
                background:
                  activeBar === i ? "var(--blue)" : "var(--muted)",
                opacity: activeBar === i ? 1 : 0.5,
              }}
              onClick={() =>
                setActiveBar(activeBar === i ? null : i)
              }
            />
          );
        })}
        <div
          className="flex-1 rounded-sm cursor-pointer"
          style={{
            height: `${Math.max(4, (today_value / maxVal) * 100)}%`,
            background:
              activeBar === todayIndex ? "var(--blue)" : todayColor,
          }}
          onClick={() =>
            setActiveBar(activeBar === todayIndex ? null : todayIndex)
          }
        />

        {activeBar !== null && (
          <div
            className="absolute left-0 right-0 text-center rounded px-2 py-1 pointer-events-none whitespace-nowrap z-10"
            style={{
              bottom: "calc(100% + 4px)",
              background: "var(--surface)",
              border: "1px solid var(--border)",
              color: "var(--text-bright)",
              fontSize: 12,
              lineHeight: "1.3",
            }}
          >
            {getTooltipText(activeBar)}
          </div>
        )}
      </div>
      <div className="flex items-center justify-between text-sm">
        <span style={{ color: "var(--muted)" }}>
          {day_count}d avg: {fmtValue(avg)}
        </span>
        <span
          className="tabular-nums font-semibold"
          style={{
            color:
              ratio !== null && ratio >= 1.5
                ? "var(--gold)"
                : "var(--text)",
          }}
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
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function I5Cell({
  is_ath,
  ath_price,
  ath_date,
  days_since_ath,
  year_high,
  year_high_date,
}: StockResult["i5"]) {
  return (
    <div className="flex gap-4 text-sm">
      {/* ATH */}
      <div className="flex flex-col gap-0.5 min-w-0 flex-1">
        <span
          className="uppercase tracking-wider"
          style={{ color: "var(--muted)", fontSize: 12 }}
        >
          ATH
        </span>
        {is_ath ? (
          <>
            <span
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded font-bold w-fit"
              style={{ background: "#3a2a10", color: "var(--gold)", fontSize: 13 }}
            >
              ATH TODAY
            </span>
            {ath_price != null && (
              <span className="tabular-nums" style={{ color: "var(--text)", fontSize: 13 }}>
                ${ath_price.toFixed(2)}
              </span>
            )}
          </>
        ) : (
          <>
            <span className="tabular-nums" style={{ color: "var(--text)" }}>
              {ath_price ? `$${ath_price.toFixed(2)}` : "N/A"}
            </span>
            {ath_date && (
              <span style={{ color: "var(--muted)", fontSize: 12 }}>
                {fmtDateShort(ath_date)}
                {days_since_ath !== null && (
                  <span style={{ opacity: 0.6 }}> ({days_since_ath}d)</span>
                )}
              </span>
            )}
          </>
        )}
      </div>

      <div style={{ borderLeft: "1px solid var(--border)" }} />

      {/* 52W High */}
      <div className="flex flex-col gap-0.5 min-w-0 flex-1">
        <span
          className="uppercase tracking-wider"
          style={{ color: "var(--muted)", fontSize: 12 }}
        >
          52W High
        </span>
        <span className="tabular-nums" style={{ color: "var(--text)" }}>
          {year_high ? `$${year_high.toFixed(2)}` : "N/A"}
        </span>
        {year_high_date && (
          <span style={{ color: "var(--muted)", fontSize: 12 }}>
            {fmtDateShort(year_high_date)}
          </span>
        )}
      </div>
    </div>
  );
}

function dateCountdown(
  iso: string | null
): { label: string; days: number; color: string } | null {
  if (!iso) return null;
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return null;
  const target = new Date(y, m - 1, d);
  const now = new Date();
  const today0 = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const days = Math.round((target.getTime() - today0.getTime()) / 86_400_000);
  if (days < 0) return null;

  const dateStr = target.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
  const soon = days <= 7;
  const color = soon ? "var(--gold)" : "var(--text)";
  let label: string;
  if (days === 0) label = `Today · ${dateStr}`;
  else if (days === 1) label = `Tomorrow · ${dateStr}`;
  else label = `in ${days}d · ${dateStr}`;
  return { label, days, color };
}

function EventLabel({ tag, iso }: { tag: string; iso: string | null }) {
  const info = dateCountdown(iso);
  return (
    <div className="flex items-baseline gap-2">
      <span
        className="uppercase tracking-wider shrink-0"
        style={{ color: "var(--muted)", fontSize: 12 }}
      >
        {tag}
      </span>
      {info ? (
        <span
          className="tabular-nums font-medium"
          style={{ color: info.color, fontSize: 13 }}
        >
          {info.label}
        </span>
      ) : (
        <span style={{ color: "var(--muted)", fontSize: 13 }}>—</span>
      )}
    </div>
  );
}

function GapUpRow({
  value,
  open,
  prevClose,
}: {
  value: number | null;
  open: number;
  prevClose: number;
}) {
  const [showFormula, setShowFormula] = useState(false);
  return (
    <div
      className="mt-2 pt-2 flex items-baseline gap-2"
      style={{ borderTop: "1px solid var(--border)" }}
    >
      <span
        className="uppercase tracking-wider shrink-0"
        style={{ color: "var(--muted)", fontSize: 12 }}
      >
        Gap
      </span>
      <span
        className="tabular-nums font-medium cursor-pointer"
        style={{ color: pctColor(value), fontSize: 13 }}
        onClick={() => setShowFormula((f) => !f)}
        title="Tap to show formula"
      >
        {value !== null ? fmtPct(value) : "—"}
      </span>
      {showFormula && value !== null && (
        <span className="text-xs tabular-nums" style={{ color: "var(--muted)" }}>
          ({fmtPrice(open)} − {fmtPrice(prevClose)}) / {fmtPrice(prevClose)}
        </span>
      )}
    </div>
  );
}

function EventsRow({
  earningsDate,
  dividendDate,
  exDividendDate,
}: {
  earningsDate: string | null;
  dividendDate: string | null;
  exDividendDate: string | null;
}) {
  return (
    <div
      className="mt-2 pt-2 flex items-baseline gap-x-4 gap-y-1 flex-wrap"
      style={{ borderTop: "1px solid var(--border)" }}
    >
      <EventLabel tag="Earnings" iso={earningsDate} />
      {dividendDate && <EventLabel tag="Dividend" iso={dividendDate} />}
      {exDividendDate && <EventLabel tag="Ex-Div" iso={exDividendDate} />}
    </div>
  );
}

function NewsModal({
  article,
  onClose,
}: {
  article: NewsArticle;
  onClose: () => void;
}) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  const ts = article.datetime
    ? new Date(article.datetime * 1000).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
      })
    : null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.7)" }}
      onClick={onClose}
    >
      <div
        className="rounded-lg w-full max-w-lg max-h-[80vh] overflow-y-auto p-5 relative"
        style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <button
          className="absolute top-3 right-3 w-8 h-8 flex items-center justify-center rounded-full"
          style={{ background: "var(--bg)", color: "var(--muted)" }}
          onClick={onClose}
        >
          ✕
        </button>

        <h2
          className="text-base font-semibold pr-8 leading-snug"
          style={{ color: "var(--text-bright)" }}
        >
          {article.headline}
        </h2>

        <div className="flex items-center gap-2 mt-2 text-xs" style={{ color: "var(--muted)" }}>
          {article.source && <span>{article.source}</span>}
          {article.source && ts && <span>·</span>}
          {ts && <span>{ts}</span>}
        </div>

        {article.summary && (
          <p className="mt-3 text-sm leading-relaxed" style={{ color: "var(--text)" }}>
            {article.summary}
          </p>
        )}

        {article.url && (
          <a
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-block mt-4 text-sm font-medium underline"
            style={{ color: "var(--accent, #60a5fa)" }}
          >
            Read full article →
          </a>
        )}
      </div>
    </div>
  );
}

function NewsSection({ symbol }: { symbol: string }) {
  const [open, setOpen] = useState(false);
  const [articles, setArticles] = useState<NewsArticle[]>([]);
  const [loading, setLoading] = useState(false);
  const [fetched, setFetched] = useState(false);
  const [selected, setSelected] = useState<NewsArticle | null>(null);

  const handleToggle = useCallback(() => {
    setOpen((prev) => {
      const next = !prev;
      if (next && !fetched) {
        setLoading(true);
        fetchNews(symbol)
          .then((items) => {
            setArticles(items);
            setFetched(true);
          })
          .catch(() => {})
          .finally(() => setLoading(false));
      }
      return next;
    });
  }, [symbol, fetched]);

  return (
    <div style={{ borderTop: "1px solid var(--border)" }}>
      <button
        className="flex items-center gap-2 w-full pt-3 pb-1 text-sm select-none"
        style={{ color: "var(--muted)" }}
        onClick={handleToggle}
      >
        <svg
          className="h-3.5 w-3.5 transition-transform"
          style={{ transform: open ? "rotate(90deg)" : "rotate(0deg)" }}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2.5}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>
        <span className="uppercase tracking-wider font-medium" style={{ fontSize: 12 }}>News</span>
      </button>
      {open && (
        <div className="pb-2">
          {loading && (
            <p className="text-sm italic py-1" style={{ color: "var(--muted)" }}>
              Loading…
            </p>
          )}
          {!loading && articles.length === 0 && (
            <p className="text-sm italic py-1" style={{ color: "var(--muted)" }}>
              No recent news.
            </p>
          )}
          {articles.map((a, i) => {
            const ts = a.datetime
              ? new Date(a.datetime * 1000).toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                })
              : null;
            return (
              <button
                key={i}
                className="block w-full text-left py-1.5 text-sm leading-snug hover:underline"
                style={{ color: "var(--text)" }}
                onClick={() => setSelected(a)}
              >
                {a.headline}
                {ts && (
                  <span className="ml-2" style={{ color: "var(--muted)", fontSize: 11 }}>
                    {ts}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}
      {selected && <NewsModal article={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Table
// ---------------------------------------------------------------------------

const TH = ({
  children,
  style: extraStyle,
}: {
  children: React.ReactNode;
  style?: React.CSSProperties;
}) => (
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

const TD = ({
  children,
  style: extraStyle,
}: {
  children: React.ReactNode;
  style?: React.CSSProperties;
}) => (
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

// ---------------------------------------------------------------------------
// Mobile card (shown < md)
// ---------------------------------------------------------------------------

function CardStat({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1 min-w-0">
      <span
        className="uppercase tracking-wider"
        style={{ color: "var(--muted)", fontSize: 11 }}
      >
        {label}
      </span>
      {children}
    </div>
  );
}

function StockCard({ stock }: { stock: StockResult }) {
  return (
    <div
      className="rounded-lg p-4 space-y-4"
      style={{
        border: "1px solid var(--border)",
        background: "var(--surface)",
      }}
    >
      {/* Symbol + price */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-baseline gap-2.5 min-w-0">
          <span
            className="tabular-nums shrink-0"
            style={{ color: "var(--muted)", fontSize: 14 }}
          >
            #{stock.rank}
          </span>
          <span
            className="font-bold tracking-wide truncate"
            style={{ color: "var(--text-bright)", fontSize: 22 }}
          >
            {stock.symbol}
          </span>
          {fmtMarketCap(stock.market_cap) && (
            <span
              className="tabular-nums shrink-0"
              style={{ color: "var(--muted)", fontSize: 12 }}
              title="Market capitalisation"
            >
              {fmtMarketCap(stock.market_cap)}
            </span>
          )}
          {stock.scrape_error && (
            <span
              className="shrink-0"
              style={{ color: "var(--gold)", fontSize: 12 }}
              title={stock.scrape_error}
            >
              partial
            </span>
          )}
        </div>
        <span
          className="tabular-nums font-semibold shrink-0"
          style={{ color: "var(--text-bright)", fontSize: 22 }}
        >
          {fmtPrice(stock.rt_price)}
        </span>
      </div>

      {/* I1 / I2 / I3 — tap any value to see formula */}
      <div className="grid grid-cols-3 gap-3">
        <CardStat label="I1 · vs Open">
          <TappablePct value={stock.i1} formula={i1Formula(stock)} />
        </CardStat>
        <CardStat label="I2 · vs Prev">
          <TappablePct value={stock.i2} formula={i2Formula(stock)} />
        </CardStat>
        <CardStat label="I3 · in Candle">
          <TappableI3 value={stock.i3} formula={i3Formula(stock)} />
        </CardStat>
      </div>

      {/* I4 */}
      <CardStat label="I4 · Volume (15d)">
        <I4Cell {...stock.i4} />
      </CardStat>

      {/* I5 + gap up + earnings countdown */}
      <div className="pt-3" style={{ borderTop: "1px solid var(--border)" }}>
        <I5Cell {...stock.i5} />
        <GapUpRow value={stock.gap_up_pct} open={stock.open_price} prevClose={stock.prev_close} />
        <EventsRow
          earningsDate={stock.next_earnings_date}
          dividendDate={stock.next_dividend_date}
          exDividendDate={stock.ex_dividend_date}
        />
      </div>

      {/* News — on-demand fetch */}
      <NewsSection symbol={stock.symbol} />
    </div>
  );
}

function I6Footer({ stock }: { stock: StockResult }) {
  return (
    <div
      className="rounded-lg px-4 py-3 flex flex-wrap gap-x-6 gap-y-1"
      style={{
        border: "1px solid var(--border)",
        background: "var(--surface)",
        fontSize: 14,
      }}
    >
      <span style={{ color: "var(--muted)" }}>
        I6 — NASDAQ from open:{" "}
        <span
          className="tabular-nums font-semibold"
          style={{ color: pctColor(stock.i6.nasdaq_from_open_pct) }}
        >
          {fmtPct(stock.i6.nasdaq_from_open_pct)}
        </span>
      </span>
      <span style={{ color: "var(--muted)" }}>
        from prev close:{" "}
        <span
          className="tabular-nums font-semibold"
          style={{ color: pctColor(stock.i6.nasdaq_from_prev_close_pct) }}
        >
          {fmtPct(stock.i6.nasdaq_from_prev_close_pct)}
        </span>
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

export default function CandidatesTable({ stocks }: { stocks: StockResult[] }) {
  if (stocks.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded-lg"
        style={{
          height: 200,
          color: "var(--muted)",
          fontSize: 16,
          border: "1px solid var(--border)",
        }}
      >
        No data — tap Refresh to load
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Mobile: stacked cards */}
      <div className="md:hidden space-y-3">
        {stocks.map((stock) => (
          <StockCard key={stock.symbol} stock={stock} />
        ))}
      </div>

      {/* Desktop / tablet: full table */}
      <div
        className="hidden md:block overflow-x-auto rounded-lg"
        style={{ border: "1px solid var(--border)" }}
      >
        <table className="w-full border-collapse text-left">
          <thead style={{ background: "var(--surface)" }}>
            <tr>
              <TH>#</TH>
              <TH>Symbol</TH>
              <TH>Price</TH>
              <TH style={{ minWidth: 150 }}>I1 — Close vs Open</TH>
              <TH style={{ minWidth: 160 }}>I2 — Close vs Prev</TH>
              <TH style={{ minWidth: 160 }}>I3 — Close in Candle</TH>
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
                onMouseEnter={(e) =>
                  (e.currentTarget.style.background =
                    "rgba(255,255,255,0.02)")
                }
                onMouseLeave={(e) =>
                  (e.currentTarget.style.background = "transparent")
                }
              >
                <TD>
                  <span
                    className="tabular-nums"
                    style={{ color: "var(--muted)", fontSize: 14 }}
                  >
                    {stock.rank}
                  </span>
                </TD>

                <TD>
                  <div className="flex flex-col">
                    <div className="flex items-baseline gap-1.5">
                      <span
                        className="font-bold tracking-wide"
                        style={{
                          color: "var(--text-bright)",
                          fontSize: 16,
                        }}
                      >
                        {stock.symbol}
                      </span>
                      {fmtMarketCap(stock.market_cap) && (
                        <span
                          className="tabular-nums"
                          style={{ color: "var(--muted)", fontSize: 11 }}
                          title="Market capitalisation"
                        >
                          {fmtMarketCap(stock.market_cap)}
                        </span>
                      )}
                    </div>
                    {stock.scrape_error && (
                      <span
                        style={{ color: "var(--gold)", fontSize: 13 }}
                        title={stock.scrape_error}
                      >
                        partial
                      </span>
                    )}
                  </div>
                </TD>

                <TD>
                  <span
                    className="tabular-nums font-semibold"
                    style={{
                      color: "var(--text-bright)",
                      fontSize: 16,
                    }}
                  >
                    {fmtPrice(stock.rt_price)}
                  </span>
                </TD>

                {/* I1 — tap to see formula */}
                <TD>
                  <TappablePct
                    value={stock.i1}
                    formula={i1Formula(stock)}
                  />
                </TD>

                {/* I2 — tap to see formula */}
                <TD>
                  <TappablePct
                    value={stock.i2}
                    formula={i2Formula(stock)}
                  />
                </TD>

                {/* I3 — tap to see formula */}
                <TD>
                  <TappableI3
                    value={stock.i3}
                    formula={i3Formula(stock)}
                  />
                </TD>

                {/* I4 */}
                <TD>
                  <I4Cell {...stock.i4} />
                </TD>

                {/* I5 + gap up + earnings countdown + news */}
                <TD>
                  <I5Cell {...stock.i5} />
                  <GapUpRow value={stock.gap_up_pct} open={stock.open_price} prevClose={stock.prev_close} />
                  <EventsRow
                    earningsDate={stock.next_earnings_date}
                    dividendDate={stock.next_dividend_date}
                    exDividendDate={stock.ex_dividend_date}
                  />
                  <NewsSection symbol={stock.symbol} />
                </TD>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* I6 footer */}
      <I6Footer stock={stocks[0]} />
    </div>
  );
}
