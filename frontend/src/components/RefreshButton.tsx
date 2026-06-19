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
      className="flex items-center gap-2 rounded-lg font-semibold text-base transition-all
        disabled:opacity-50 disabled:cursor-not-allowed"
      style={{
        background: loading ? "var(--border)" : "#4a7c40",
        color: loading ? "var(--muted)" : "#d6ecd0",
        padding: "12px 24px",
        minHeight: 48,
      }}
    >
      {loading ? (
        <>
          <svg
            className="animate-spin h-5 w-5"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12" cy="12" r="10"
              stroke="currentColor" strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8v8H4z"
            />
          </svg>
          Fetching…
        </>
      ) : (
        <>
          <svg
            className="h-5 w-5"
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
          >
            <path
              strokeLinecap="round" strokeLinejoin="round"
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
          Refresh
        </>
      )}
    </button>
  );
}
