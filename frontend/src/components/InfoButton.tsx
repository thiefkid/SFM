"use client";

import { useEffect, useState } from "react";
import type { BackendVersion } from "@/types/dashboard";

const FE_COMMIT = process.env.NEXT_PUBLIC_GIT_COMMIT ?? "dev";
const FE_COMMIT_TIME = process.env.NEXT_PUBLIC_GIT_COMMIT_TIME ?? "";

function shortSha(sha: string): string {
  return sha && sha !== "dev" ? sha.slice(0, 7) : "dev";
}

function fmtCommitTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  });
}

function VersionRow({ label, commit, time }: { label: string; commit: string; time: string | null | undefined }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="uppercase tracking-wider" style={{ color: "var(--muted)", fontSize: 11 }}>
        {label}
      </span>
      <span className="tabular-nums font-mono" style={{ color: "var(--text-bright)", fontSize: 14 }}>
        {shortSha(commit)}
      </span>
      <span className="tabular-nums" style={{ color: "var(--muted)", fontSize: 12 }}>
        {fmtCommitTime(time)}
      </span>
    </div>
  );
}

export default function InfoButton({ backend }: { backend?: BackendVersion }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  return (
    <>
      <button
        aria-label="Version info"
        onClick={() => setOpen(true)}
        className="flex items-center justify-center rounded-full shrink-0 transition-colors"
        style={{
          width: 24,
          height: 24,
          border: "1px solid var(--border)",
          color: "var(--muted)",
          fontSize: 13,
          fontStyle: "italic",
          fontFamily: "Georgia, serif",
          lineHeight: 1,
        }}
      >
        i
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: "rgba(0,0,0,0.7)" }}
          onClick={() => setOpen(false)}
        >
          <div
            className="rounded-lg w-full max-w-xs p-5 relative"
            style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="absolute top-3 right-3 w-7 h-7 flex items-center justify-center rounded-full"
              style={{ background: "var(--bg)", color: "var(--muted)" }}
              onClick={() => setOpen(false)}
            >
              ✕
            </button>

            <h2 className="text-sm font-semibold mb-4" style={{ color: "var(--text-bright)" }}>
              Build Version
            </h2>

            <div className="flex flex-col gap-4">
              <VersionRow label="Frontend" commit={FE_COMMIT} time={FE_COMMIT_TIME} />
              <VersionRow
                label="Backend"
                commit={backend?.commit ?? "—"}
                time={backend?.commit_time}
              />
            </div>
          </div>
        </div>
      )}
    </>
  );
}
