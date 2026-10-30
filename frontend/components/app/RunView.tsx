"use client";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { AlertCircle, Check, Loader2 } from "lucide-react";
import { Eyebrow } from "../landing/UI";
import {
  api,
  money,
  pct,
  providerLabel,
  type CrowdSummary,
  type HandsSession,
  type HandsStep,
  type PersonaLite,
  type Reaction,
  type RunInfo,
} from "@/lib/api";
import CrowdWall, { type Member } from "./CrowdWall";
import SummaryPanel from "./SummaryPanel";
import DocsPanel from "./DocsPanel";
import HandsPanel from "./HandsPanel";

const STAGES = [
  ["crowd", "Crowd"],
  ["summary", "Signal"],
  ["docs", "Architect"],
  ["hands", "Hands"],
  ["done", "Report"],
] as const;
type Stage = (typeof STAGES)[number][0];

export type LiveSession = Partial<HandsSession> & {
  persona_id: string;
  persona_name: string;
  steps: HandsStep[];
};

export default function RunView() {
  const id = useSearchParams().get("id") ?? "";
  const [info, setInfo] = useState<RunInfo | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState<CrowdSummary | null>(null);
  const [docs, setDocs] = useState<{ brd_md: string; prd_md: string } | null>(null);
  const [sessions, setSessions] = useState<Record<string, LiveSession>>({});
  const [stage, setStage] = useState<Stage>("crowd");
  const [status, setStatus] = useState<RunInfo["status"]>("queued");
  const [error, setError] = useState<string | null>(null);
  const [degraded, setDegraded] = useState(0);
  const [labels, setLabels] = useState<Record<string, string>>({});
  const buffer = useRef<Member[]>([]);

  useEffect(() => {
    api
      .archetypes()
      .then((list) => setLabels(Object.fromEntries(list.map((a) => [a.id, a.label]))))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!id) return;
    let closed = false;
    api.run(id).then(setInfo).catch((e) => setError(String(e.message ?? e)));

    // Reactions arrive hundreds per second; flush them to React in batches.
    const flush = setInterval(() => {
      if (buffer.current.length) {
        const batch = buffer.current;
        buffer.current = [];
        setMembers((m) => [...m, ...batch]);
      }
    }, 120);

    const es = new EventSource(api.eventsUrl(id));
    const on = <T,>(type: string, fn: (d: T) => void) =>
      es.addEventListener(type, (e) => fn(JSON.parse((e as MessageEvent).data)));

    on("run.started", () => setStatus("running"));
    on<{ size: number }>("crowd.assembled", (d) => setTotal(d.size));
    on("reaction", (d: { persona: PersonaLite; reaction: Reaction }) => buffer.current.push(d));
    on<{ personas: number }>("crowd.degraded", (d) => setDegraded((n) => n + d.personas));
    on("summary", (d: CrowdSummary) => {
      setSummary(d);
      setStage("docs");
    });
    on<{ brd_md: string; prd_md: string }>("docs", (d) => {
      setDocs(d);
      setStage("hands");
    });
    on("hands.step", (d: { persona_id: string; name: string; step: HandsStep }) =>
      setSessions((s) => {
        const cur = s[d.persona_id] ?? { persona_id: d.persona_id, persona_name: d.name, steps: [] };
        return { ...s, [d.persona_id]: { ...cur, steps: [...cur.steps, d.step] } };
      }),
    );
    on("hands.session", (d: HandsSession) =>
      setSessions((s) => ({ ...s, [d.persona_id]: { ...s[d.persona_id], ...d, steps: s[d.persona_id]?.steps ?? [] } })),
    );
    on<{ stage: string }>("stage.done", (d) => {
      if (d.stage === "crowd") setStage("summary");
    });
    on("run.finished", () => {
      es.close();
      // replayed runs finish in one burst, before the flush timer fires
      const rest = buffer.current;
      buffer.current = [];
      if (rest.length) setMembers((m) => [...m, ...rest]);
      setStatus("finished");
      setStage("done");
      api.hands(id).then((list) => {
        if (!closed) setSessions(Object.fromEntries(list.map((x) => [x.persona_id, x])));
      });
    });
    on<{ error: string }>("run.failed", (d) => {
      es.close();
      setStatus("failed");
      setError(d.error);
    });
    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED) setError("Lost the connection to the Crowdpod server.");
    };
    return () => {
      closed = true;
      es.close();
      clearInterval(flush);
    };
  }, [id]);

  if (!id) return <p className="app-empty">No simulation selected.</p>;
  const brief = info?.request.brief;
  const done = members.length;
  const handsWanted = !!info?.request.hands;
  const stageIndex = STAGES.findIndex(([s]) => s === stage);

  return (
    <div className="run-view">
      <section className="app-card run-head">
        <Eyebrow>SIMULATION · {id}</Eyebrow>
        <div className="run-title">
          <h1>{brief?.name ?? "…"}</h1>
          <span className={`status-pill ${status}`}>
            {status === "running" && <Loader2 className="spin" size={13} />}
            {status === "finished" && <Check size={13} />}
            {status}
          </span>
        </div>
        {brief && <p className="run-pitch">{brief.pitch}</p>}
        <div className="run-meta">
          {info && <span>{providerLabel(info.provider)}</span>}
          {brief && <span>{brief.price_period === "free" || !brief.price ? "Free" : `${money(brief.price)} ${brief.price_period.replace("_", "-")}`}</span>}
          {brief?.target_hint && <span>You guessed: {brief.target_hint}</span>}
        </div>
        <ol className="stage-track" aria-label="Progress">
          {STAGES.filter(([s]) => s !== "hands" || handsWanted).map(([s, label]) => {
            const i = STAGES.findIndex(([x]) => x === s);
            const state = i < stageIndex || stage === "done" ? "done" : i === stageIndex ? "now" : "";
            return (
              <li key={s} className={state}>
                <i>{state === "done" ? <Check size={12} /> : i + 1}</i>
                {label}
              </li>
            );
          })}
        </ol>
        <div className="crowd-progress" aria-label={`${done} of ${total} reactions`}>
          <span style={{ width: total ? `${(done / total) * 100}%` : "0%" }} />
        </div>
        <small className="crowd-count">
          {done.toLocaleString("en-IN")} / {total.toLocaleString("en-IN")} people have reacted
          {summary && ` · ${pct(summary.adoption_rate)} would adopt`}
        </small>
        {degraded > 0 && (
          <p className="form-error">
            <AlertCircle size={14} /> The model failed for {degraded} people; their answers came from the offline simulation.
          </p>
        )}
        {error && (
          <p className="form-error" role="alert">
            <AlertCircle size={14} /> {error}
          </p>
        )}
      </section>

      <CrowdWall runId={id} members={members} total={total} product={brief?.name ?? "it"} labels={labels} />
      {summary && <SummaryPanel summary={summary} />}
      {docs && <DocsPanel docs={docs} name={brief?.name ?? "idea"} />}
      {handsWanted && (
        <HandsPanel
          runId={id}
          sessions={Object.values(sessions)}
          url={info?.request.hands?.url ?? ""}
          labels={labels}
        />
      )}
      <p className="sim-note">
        Crowdpod simulates people. Use it to decide who to talk to first and what to ask them, then confirm with real people.
      </p>
    </div>
  );
}
