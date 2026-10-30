"use client";
import { useState } from "react";
import { ArrowDown, ArrowLeft, Check, LogOut, MousePointerClick, Type, X } from "lucide-react";
import { api } from "@/lib/api";
import type { LiveSession } from "./RunView";

const ICONS = { click: MousePointerClick, type: Type, scroll: ArrowDown, back: ArrowLeft, done: Check, give_up: LogOut };
const OUTCOME: Record<string, string> = {
  success: "Found it",
  gave_up: "Gave up",
  step_limit: "Still looking",
  error: "Session failed",
};

export default function HandsPanel({
  runId,
  sessions,
  url,
  labels,
}: {
  runId: string;
  sessions: LiveSession[];
  url: string;
  labels: Record<string, string>;
}) {
  // live step events carry only the persona id: <run>-<archetype>-<n>
  const segment = (s: LiveSession) => {
    const id = s.archetype_id ?? s.persona_id.split("-").slice(1, -1).join("-");
    return labels[id] ?? id.replace(/-/g, " ");
  };
  const [openId, setOpenId] = useState<string | null>(null);
  const open = sessions.find((s) => s.persona_id === openId) ?? sessions[0];
  const [stepIdx, setStepIdx] = useState<number | null>(null);
  const step = open ? open.steps[stepIdx ?? open.steps.length - 1] : undefined;

  return (
    <section className="app-card hands-section">
      <span className="mini-label">THE HANDS</span>
      <h2>
        They opened <em>{url.replace(/^https?:\/\//, "").replace(/\/$/, "")}</em>
      </h2>
      {sessions.length === 0 ? (
        <p className="app-empty">Browsers start after the architect finishes…</p>
      ) : (
        <div className="hands-layout">
          <ul className="session-list">
            {sessions.map((s) => (
              <li key={s.persona_id}>
                <button
                  className={s.persona_id === open?.persona_id ? "on" : ""}
                  onClick={() => {
                    setOpenId(s.persona_id);
                    setStepIdx(null);
                  }}
                >
                  <strong>{s.persona_name}</strong>
                  <small>{segment(s)}</small>
                  <span className={`outcome ${s.outcome ?? "running"}`}>
                    {s.outcome ? OUTCOME[s.outcome] : `step ${s.steps.length}`}
                  </span>
                  {s.summary && <p>{s.summary}</p>}
                </button>
              </li>
            ))}
          </ul>
          {open && (
            <div className="session-detail">
              {open.goal && <p className="goal">Goal: {open.goal}</p>}
              <div className="shot">
                {step?.screenshot ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={api.artifactUrl(runId, `shots/${step.screenshot}`)} alt={`What ${open.persona_name} saw at step ${step.index + 1}`} />
                ) : (
                  <span className="app-empty">No screenshot</span>
                )}
              </div>
              <ol className="step-list">
                {open.steps.map((s, i) => {
                  const Icon = ICONS[s.action] ?? X;
                  return (
                    <li key={i}>
                      <button className={step === s ? "on" : ""} onClick={() => setStepIdx(i)}>
                        <span className="step-time">{s.t.toFixed(0)}s</span>
                        <Icon size={14} />
                        <span>
                          <b>
                            {s.action.replace("_", " ")}
                            {s.target_label ? ` “${s.target_label}”` : ""}
                          </b>
                          {s.thought && <em>“{s.thought}”</em>}
                          {s.error && <small className="step-error">{s.error}</small>}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ol>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
