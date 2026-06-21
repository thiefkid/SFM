import type { NextConfig } from "next";
import { execSync } from "child_process";

// Resolve the frontend's git commit + commit timestamp at build time. On Vercel
// the repo is checked out, so git works; we also honour Vercel's system env vars
// and fall back to "dev"/build-time so local builds never fail.
function gitInfo(): { commit: string; commitTime: string } {
  let commit = process.env.VERCEL_GIT_COMMIT_SHA || "";
  let commitTime = "";
  try {
    if (!commit) commit = execSync("git rev-parse HEAD").toString().trim();
    commitTime = execSync(`git show -s --format=%cI ${commit}`).toString().trim();
  } catch {
    // ignore — fall back below
  }
  return {
    commit: commit || "dev",
    commitTime: commitTime || new Date().toISOString(),
  };
}

const git = gitInfo();

const nextConfig: NextConfig = {
  env: {
    NEXT_PUBLIC_GIT_COMMIT: git.commit,
    NEXT_PUBLIC_GIT_COMMIT_TIME: git.commitTime,
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.BACKEND_URL || "http://localhost:8000"}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
