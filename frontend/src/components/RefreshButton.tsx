"use client";

interface Props {
  loading: boolean;
  onClick: () => void;
}

export default function RefreshButton({ loading, onClick }: Props) {
  return (
    <button
      onClick={onClick}
      disabled={loading}
      className="flex items-center justify-center rounded-full transition-all
        disabled:opacity-50 disabled:cursor-not-allowed"
      style={{
        width: 36,
        height: 36,
        background: loading ? "var(--border)" : "rgba(74, 124, 64, 0.25)",
        color: loading ? "var(--muted)" : "var(--green)",
      }}
      title={loading ? "Refreshing…" : "Refresh data"}
    >
      <svg
        className={`h-4 w-4 ${loading ? "animate-spin" : ""}`}
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={2.5}
      >
        {loading ? (
          <>
            <circle
              className="opacity-25"
              cx="12" cy="12" r="10"
              stroke="currentColor" strokeWidth="4" fill="none"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              stroke="none"
              d="M4 12a8 8 0 018-8v8H4z"
            />
          </>
        ) : (
          <path
            strokeLinecap="round" strokeLinejoin="round"
            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
          />
        )}
      </svg>
    </button>
  );
}
