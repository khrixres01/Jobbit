"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "@/lib/supabase";

const NAV = [
  { href: "/", label: "Overview", icon: "▦" },
  { href: "/applications", label: "Applications", icon: "☰" },
  { href: "/runs", label: "Pipeline runs", icon: "↻" },
];

export default function AuthGate({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null | undefined>(undefined);
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pathname = usePathname();

  useEffect(() => {
    const sb = supabase();
    sb.auth.getSession().then(({ data }) => setSession(data.session));
    const { data: sub } = sb.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => sub.subscription.unsubscribe();
  }, []);

  if (session === undefined) return <div className="boot">Loading…</div>;

  if (!session) {
    const send = async (e: React.FormEvent) => {
      e.preventDefault();
      setError(null);
      const { error } = await supabase().auth.signInWithOtp({
        email, options: { emailRedirectTo: window.location.origin },
      });
      if (error) setError(error.message);
      else setSent(true);
    };
    return (
      <main className="login">
        <div className="login-card">
          <div className="brand-mark">J</div>
          <h1>Jobbit</h1>
          <p className="muted">Your remote job search, reviewed in one place.</p>
          {sent ? (
            <p className="login-sent">Check <b>{email}</b> for a sign-in link. It works once.</p>
          ) : (
            <form onSubmit={send}>
              <input type="email" required placeholder="you@example.com" value={email}
                     onChange={(e) => setEmail(e.target.value)} />
              <button className="btn btn-primary" type="submit">Send magic link</button>
            </form>
          )}
          {error && <p className="error">{error}</p>}
        </div>
      </main>
    );
  }

  const active = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));
  return (
    <div className="shell">
      <aside className="sidebar">
        <Link href="/" className="brand"><span className="brand-mark">J</span> Jobbit</Link>
        <nav>
          {NAV.map((n) => (
            <Link key={n.href} href={n.href} className={active(n.href) ? "nav-item active" : "nav-item"}>
              <span className="nav-icon" aria-hidden>{n.icon}</span>{n.label}
            </Link>
          ))}
        </nav>
        <div className="sidebar-foot">
          <span className="muted small ellipsis" title={session.user.email}>{session.user.email}</span>
          <button className="btn-link small" onClick={() => supabase().auth.signOut()}>Sign out</button>
        </div>
      </aside>
      <div className="main">{children}</div>
    </div>
  );
}
