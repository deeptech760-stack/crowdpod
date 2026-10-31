"use client";
import { useMemo, useState, type FormEvent } from "react";
import { Loader2, MessageCircle, Send } from "lucide-react";
import { api, priced, type PersonaLite, type Reaction, type Verdict } from "@/lib/api";

export type Member = { persona: PersonaLite; reaction: Reaction };

const VERDICTS: [Verdict | "all", string][] = [
  ["all", "Everyone"],
  ["adopt", "Adopt"],
  ["maybe", "Maybe"],
  ["reject", "Reject"],
];

export default function CrowdWall({
  runId,
  members,
  total,
  product,
  labels,
  unit,
}: {
  runId: string;
  members: Member[];
  total: number;
  product: string;
  labels: Record<string, string>;
  unit: "one_time" | "month";
}) {
  const label = (id: string) => labels[id] ?? id.replace(/-/g, " ");
  const [filter, setFilter] = useState<Verdict | "all">("all");
  const [selected, setSelected] = useState<Member | null>(null);
  const counts = useMemo(() => {
    const c = { adopt: 0, maybe: 0, reject: 0 };
    members.forEach((m) => c[m.reaction.verdict]++);
    return c;
  }, [members]);
  const latest = members.slice(-5).reverse();
  const focus = selected ?? latest[0] ?? null;

  return (
    <section className="app-card crowd-section">
      <div className="crowd-head">
        <div>
          <span className="mini-label">THE CROWD</span>
          <h2>
            {total ? total.toLocaleString("en-IN") : "…"} people, <em>no politeness.</em>
          </h2>
        </div>
        <div className="chip-row" role="group" aria-label="Filter by verdict">
          {VERDICTS.map(([v, label]) => (
            <button
              key={v}
              className={`chip ${filter === v ? "on" : ""}`}
              aria-pressed={filter === v}
              onClick={() => setFilter(v)}
            >
              {label}
              {v !== "all" && <b>{counts[v]}</b>}
            </button>
          ))}
        </div>
      </div>
      <div className="crowd-layout">
        <div className="crowd-wall" aria-label="Each square is one simulated person; select one to read their reaction">
          {members.map((m) => (
            <button
              key={m.persona.id}
              className={`tile ${m.reaction.verdict} ${filter !== "all" && filter !== m.reaction.verdict ? "dim" : ""} ${
                focus?.persona.id === m.persona.id ? "focus" : ""
              }`}
              title={`${m.persona.name}, ${m.persona.age}: ${m.reaction.verdict}`}
              aria-label={`${m.persona.name}, ${m.persona.age}, ${m.reaction.verdict}`}
              onClick={() => setSelected(m)}
            />
          ))}
          {Array.from({ length: Math.max(0, Math.min(total, 2000) - members.length) }, (_, i) => (
            <span key={`p${i}`} className="tile pending" />
          ))}
        </div>
        <div className="crowd-side">
          {focus ? (
            <PersonaCard key={focus.persona.id} runId={runId} m={focus} product={product} segment={label(focus.persona.archetype_id)} unit={unit} />
          ) : (
            <p className="app-empty">Waiting for the first reaction…</p>
          )}
          {!selected && latest.length > 1 && (
            <ul className="quote-feed" aria-live="polite">
              {latest.slice(1).map((m) => (
                <li key={m.persona.id} className={m.reaction.verdict} onClick={() => setSelected(m)}>
                  “{m.reaction.quote}” <small>— {m.persona.name}, {label(m.persona.archetype_id)}</small>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}

function PersonaCard({
  runId,
  m,
  product,
  segment,
  unit,
}: {
  runId: string;
  m: Member;
  product: string;
  segment: string;
  unit: "one_time" | "month";
}) {
  const [q, setQ] = useState("");
  const [chat, setChat] = useState<[string, string][]>([]);
  const [busy, setBusy] = useState(false);
  const ask = async (e: FormEvent) => {
    e.preventDefault();
    if (!q.trim()) return;
    const question = q.trim();
    setQ("");
    setBusy(true);
    try {
      const { answer } = await api.interview(runId, m.persona.id, question);
      setChat((c) => [...c, [question, answer]]);
    } catch (err) {
      setChat((c) => [...c, [question, `(${err instanceof Error ? err.message : "failed"})`]]);
    }
    setBusy(false);
  };
  const r = m.reaction;
  return (
    <article className={`persona-card ${r.verdict}`}>
      <header>
        <strong>
          {m.persona.name}, {m.persona.age}
        </strong>
        <span className={`verdict ${r.verdict}`}>{r.verdict}</span>
      </header>
      <small>
        {segment} · {m.persona.mood}
      </small>
      <blockquote>“{r.quote}”</blockquote>
      <dl>
        <dt>Would pay</dt>
        <dd>{priced(r.willingness_to_pay, unit)}</dd>
        {r.top_objection && (
          <>
            <dt>Biggest objection</dt>
            <dd>{r.top_objection}</dd>
          </>
        )}
        {r.must_have && (
          <>
            <dt>Must have</dt>
            <dd>{r.must_have}</dd>
          </>
        )}
      </dl>
      {chat.map(([qq, a], i) => (
        <div className="interview" key={i}>
          <p className="chat-user">{qq}</p>
          <p className="chat-ai">{a}</p>
        </div>
      ))}
      <form className="ask" onSubmit={ask}>
        <MessageCircle size={15} />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={`Ask ${m.persona.name} about ${product}…`}
          aria-label={`Ask ${m.persona.name} a question`}
        />
        <button type="submit" disabled={busy} aria-label="Send question">
          {busy ? <Loader2 className="spin" size={15} /> : <Send size={15} />}
        </button>
      </form>
    </article>
  );
}
