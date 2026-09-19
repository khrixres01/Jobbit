import fs from "node:fs";
import path from "node:path";
import type { NextConfig } from "next";

// Next.js never lets .env.local override variables already set in the shell, and this machine's
// shells can carry NEXT_PUBLIC_SUPABASE_* from another project. Make this project's .env.local win.
// (No .env.local exists on Vercel, so its dashboard settings apply there.)
const local = path.join(__dirname, ".env.local");
if (fs.existsSync(local)) {
  for (const line of fs.readFileSync(local, "utf8").split(/\r?\n/)) {
    const m = line.match(/^\s*(NEXT_PUBLIC_[A-Z0-9_]+)\s*=\s*(.*?)\s*$/);
    if (m) process.env[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
}

const nextConfig: NextConfig = {};

export default nextConfig;
