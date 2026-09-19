"use client";

import { useEffect, useState, type ReactNode } from "react";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "@/lib/supabase";

export default function AuthGate({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null | undefined>(undefined);
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const sb = supabase();
    sb.auth.getSession().then(({ data }) => setSession(data.session));
    const { data: sub } = sb.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => sub.subscription.unsubscribe();
  }, []);

  if (session === undefined) return <p className="muted pad">Loading…</p>;

  if (!session) {
    const send = async (e: React.FormEvent) => {
      e.preventDefault();
      setError(null);
      const { error } = await supabase().auth.signInWithOtp({
        email,
        options: { emailRedirectTo: window.location.origin },
      });
      if (error) setError(error.message);
      else setSent(true);
    };
    return (
      <main className="login">
        <h1>Jobbit</h1>
        {sent ? (
          <p>Check <b>{email}</b> for a sign-in link.</p>
        ) : (
          <form onSubmit={send}>
            <input type="email" required placeholder="you@example.com" value={email}
                   onChange={(e) => setEmail(e.target.value)} />
            <button type="submit">Send magic link</button>
          </form>
        )}
        {error && <p className="error">{error}</p>}
      </main>
    );
  }

  return (
    <>
      <header className="topbar">
        <a href="/" className="brand">Jobbit</a>
        <span className="muted">{session.user.email}</span>
        <button className="link" onClick={() => supabase().auth.signOut()}>Sign out</button>
      </header>
      {children}
    </>
  );
}
