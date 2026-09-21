"use client";

import { useState } from "react";
import type { FunnelStage } from "@/lib/data";

// The first stage (everything ingested) is orders of magnitude larger than the rest, so it is shown as a
// headline figure and the remaining stages share one linear scale. Single series, one hue: thin bars
// anchored to the left baseline with rounded data-ends, direct value labels, per-bar hover tooltip.
export default function Funnel({ stages }: { stages: FunnelStage[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const [head, ...rest] = stages;
  const max = Math.max(1, ...rest.map((s) => s.value));

  return (
    <div>
      <p className="funnel-head">
        <b>{head.value.toLocaleString()}</b> <span className="muted">{head.label.toLowerCase()} · {head.hint.toLowerCase()}</span>
      </p>
      <div className="funnel" role="table" aria-label="Pipeline funnel">
        {rest.map((s, i) => {
          const prev = i === 0 ? head : rest[i - 1];
          const pct = prev.value ? (s.value / prev.value) * 100 : 0;
          const pctText = pct > 0 && pct < 1 ? "<1" : String(Math.round(pct));
          const width = s.value === 0 ? 0 : Math.max(1, (s.value / max) * 100);
          return (
            <div key={s.key} className="funnel-row" role="row" tabIndex={0}
                 onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}
                 onFocus={() => setHover(i)} onBlur={() => setHover(null)}>
              <div className="funnel-label" role="rowheader">{s.label}</div>
              <div className="funnel-track" role="cell">
                <div className="funnel-area"><div className="funnel-bar" style={{ width: `${width}%` }} /></div>
                <span className="funnel-value">{s.value.toLocaleString()}</span>
                {hover === i && (
                  <div className="tooltip" role="tooltip">
                    <b>{s.label}: {s.value.toLocaleString()}</b>
                    <span> · {pctText}% of {prev.label.toLowerCase()}</span>
                    <div className="muted">{s.hint}</div>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
