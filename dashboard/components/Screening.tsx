"use client";

import { useState } from "react";
import { supabase } from "@/lib/supabase";
import type { ScreeningAnswer } from "@/lib/types";

const SOURCE_NOTE: Record<string, string> = {
  profile: "From your personal.yaml settings",
  ai: "Drafted by AI from your master profile",
  ai_flagged: "Drafted by AI — the fabrication guard flagged something, read it closely",
  edited: "Edited by you",
};

export default function Screening({ id, answers, onSaved }:
  { id: string; answers: ScreeningAnswer[]; onSaved: () => void }) {
  const [draft, setDraft] = useState<ScreeningAnswer[]>(answers);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);

  const update = (i: number, text: string) => {
    const next = [...draft];
    next[i] = { ...next[i], answer: text, edited: text !== answers[i].answer, source: "edited" };
    setDraft(next);
    setDirty(true);
  };

  const save = async () => {
    setSaving(true);
    const { error } = await supabase().from("applications").update({ screening_answers: draft }).eq("id", id);
    setSaving(false);
    if (error) alert(error.message);
    else { setDirty(false); onSaved(); }
  };

  const blanks = draft.filter((a) => !a.answer.trim()).length;
  const flagged = draft.filter((a) => a.source === "ai_flagged").length;

  return (
    <section className="card">
      <div className="card-head">
        <h2>Screening answers</h2>
        <button className="btn btn-sm btn-primary" disabled={!dirty || saving} onClick={save}>
          {saving ? "Saving…" : dirty ? "Save changes" : "Saved"}
        </button>
      </div>
      <p className="muted small">
        Used to fill application forms. Edit anything you'd word differently — nothing is submitted until you click Apply.
        {blanks > 0 && <> <b>{blanks} left blank</b>; a form asking those will be handed back to you.</>}
        {flagged > 0 && <> <b>{flagged} flagged</b> by the fabrication guard.</>}
      </p>
      <div className="qa">
        {draft.map((a, i) => (
          <div key={a.key} className={a.source === "ai_flagged" ? "qa-item qa-flagged" : "qa-item"}>
            <label htmlFor={`q-${a.key}`}>{a.question}</label>
            <textarea id={`q-${a.key}`} value={a.answer} rows={Math.min(6, Math.max(2, Math.ceil(a.answer.length / 80)))}
                      placeholder="Left blank — the applier will hand this one to you"
                      onChange={(e) => update(i, e.target.value)} />
            <span className="muted small">{SOURCE_NOTE[a.source] ?? a.source}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
