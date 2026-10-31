"use client";
import { ExternalLink, Globe, Info, Loader2, NotebookPen } from "lucide-react";
import { money, pct, type GeneratedPersonaCard, type Research } from "@/lib/api";

const span = ([lo, hi]: [number, number]) => (lo === hi ? money(lo) : `${money(lo)}–${money(hi)}`);

export default function AudiencePanel({
  research,
  personas,
  skipped,
  working,
  unit,
}: {
  research: Research | null;
  personas: GeneratedPersonaCard[];
  skipped: string | null;
  working: boolean;
  unit: "one_time" | "month";
}) {
  return (
    <section className="app-card audience-section">
      <span className="mini-label">
        <Globe size={13} /> RESEARCH & AUDIENCE
      </span>
      <h2>
        Who this idea <em>is really for.</em>
      </h2>

      {skipped && (
        <p className="notice">
          <Info size={15} /> {skipped}
        </p>
      )}
      {!research && !skipped && working && (
        <p className="app-empty">
          <Loader2 className="spin" size={14} /> Researching the market and designing personas…
        </p>
      )}

      {research && (
        <div className="research">
          <span className={`source-badge ${research.grounded ? "live" : ""}`}>
            {research.grounded
              ? `Live web search · ${research.sources.length} sources`
              : "From the model's own knowledge · not live web search"}
          </span>
          <p className="research-summary">{research.summary}</p>
          <div className="two-lists">
            {research.price_points.length > 0 && (
              <div>
                <h3>What comparable products cost</h3>
                <ul className="plain-list">
                  {research.price_points.map((x) => (
                    <li key={x}>{x}</li>
                  ))}
                </ul>
              </div>
            )}
            {research.facts.length > 0 && (
              <div>
                <h3>What the research found</h3>
                <ul className="plain-list">
                  {research.facts.map((x) => (
                    <li key={x}>{x}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
          {research.sources.length > 0 && (
            <details className="sources">
              <summary>Sources ({research.sources.length})</summary>
              <ul>
                {research.sources.map((s) => (
                  <li key={s.url}>
                    <a href={s.url} target="_blank" rel="noopener noreferrer">
                      {s.title || s.url} <ExternalLink size={12} />
                    </a>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}

      {personas.length > 0 && (
        <div className="generated-grid">
          {personas.map((p) => (
            <article key={p.id} className="generated-card">
              <header>
                <strong>{p.label}</strong>
                <span className="share">{pct(p.share)} of the market</span>
              </header>
              <small>
                {p.profession}
                {p.city ? `, ${p.city}` : ""} · {p.age[0]}–{p.age[1]} yrs
              </small>
              <dl>
                <dt>{unit === "one_time" ? "Would spend on a purchase like this" : "Monthly spend on apps"}</dt>
                <dd>{span(unit === "one_time" ? p.purchase_budget : p.budget_month)}</dd>
                {p.objections[0] && (
                  <>
                    <dt>Why they’d say no</dt>
                    <dd>{p.objections.slice(0, 2).join("; ")}</dd>
                  </>
                )}
                {p.must_haves[0] && (
                  <>
                    <dt>What would win them</dt>
                    <dd>{p.must_haves.slice(0, 2).join("; ")}</dd>
                  </>
                )}
              </dl>
              {p.evidence[0] && <p className="evidence">Based on: {p.evidence[0]}</p>}
              {p.note && (
                <p className="note-path">
                  <NotebookPen size={12} /> vault/{p.note}
                </p>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
