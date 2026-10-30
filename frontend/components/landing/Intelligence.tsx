"use client";
import { useState } from "react";
import {
  Check,
  Circle,
  MousePointerClick,
  PenTool,
  Sparkles,
  UsersRound,
} from "lucide-react";
import { AnimatedSample, DemoLabel, Eyebrow } from "./UI";
export default function Intelligence() {
  const [answer, setAnswer] = useState("");
  const [criteria, setCriteria] = useState(false);
  const score = 50 + (answer ? 25 : 0) + (criteria ? 25 : 0);
  return (
    <section className="section intelligence" id="features">
      <div className="section-heading" data-reveal>
        <div>
          <Eyebrow>THE ARCHITECT</Eyebrow>
          <h2>
            Not just opinions.
            <br />
            <em>What to build first.</em>
          </h2>
        </div>
        <p>
          The architect listens to the whole crowd and turns
          <br />
          the noise into a BRD and a PRD you can act on.
        </p>
      </div>
      <div className="clarification-layout" id="clarification" data-reveal>
        <div className="clarification-card">
          <div className="card-label">
            <Sparkles size={15} /> WHAT THE CROWD SAID{" "}
            <span>EXAMPLE</span>
          </div>
          <p className="raw-requirement">
            “I scrolled for forty seconds <mark>looking for the price.</mark>”
          </p>
          <div className="ambiguity">
            <span /> 31% of visitors left before finding it.
          </div>
          <h3>What should you fix first?</h3>
          <div className="choice-row">
            {["Show the price", "Cut the feature list", "Add a free tier"].map(
              (a) => (
                <button
                  key={a}
                  aria-pressed={a === answer}
                  className={a === answer ? "selected" : ""}
                  onClick={() => setAnswer(a)}
                >
                  {a}
                </button>
              ),
            )}
          </div>
          <div className="requirement-result" aria-live="polite">
            <span className="mini-label">
              PRD-001 ·{" "}
              {answer ? "FIRST THING TO BUILD" : "WAITING FOR YOUR INPUT"}
            </span>
            <AnimatedSample sampleKey={answer}>
              <p>
                {answer
                  ? `${answer} on the landing page, then rerun the crowd to check it worked.`
                  : "Choose a fix to turn a complaint into a requirement."}
              </p>
            </AnimatedSample>
            {answer && (
              <span className="ready-badge">
                <Check size={13} /> Prioritised
              </span>
            )}
          </div>
          <DemoLabel />
        </div>
        <div className="readiness-card">
          <span className="mini-label">HOW READY IS THIS IDEA?</span>
          <div className="score-ring">
            <svg viewBox="0 0 160 160" aria-hidden="true">
              <circle cx="80" cy="80" r="67" />
              <circle
                cx="80"
                cy="80"
                r="67"
                style={{ strokeDashoffset: 421 * (1 - score / 100) }}
              />
            </svg>
            <div aria-live="polite">
              <strong>
                {score}
                <span>%</span>
              </strong>
              <small>Launch readiness</small>
            </div>
          </div>
          <div className="readiness-checks">
            {[
              ["Market found", true],
              ["First fix chosen", !!answer],
              ["Interview questions ready", criteria],
              ["Ready for real users", !!answer && criteria],
            ].map(([label, done]) => (
              <div key={String(label)} className={done ? "done" : ""}>
                {done ? <Check size={16} /> : <Circle size={14} />}
                <span>{label}</span>
              </div>
            ))}
          </div>
          <button className="text-link" onClick={() => setCriteria(!criteria)}>
            {criteria ? "Remove interview questions" : "Add interview questions"}{" "}
            <span>{criteria ? "−" : "+"}</span>
          </button>
          {criteria && (
            <p className="criteria-copy">
              Example: “When did you last look for this, and what did you pay
              for it?”
            </p>
          )}
          <small className="score-caption">
            Illustrative score: 50% base + 25% per completed step.
          </small>
        </div>
      </div>
      <div className="feature-notes" data-reveal>
        <div>
          <UsersRound size={23} />
          <h3>A crowd.</h3>
          <p>
            Hundreds of personas, each with a budget, a mood and a reason to
            say no.
          </p>
        </div>
        <div>
          <PenTool size={23} />
          <h3>An architect.</h3>
          <p>
            A BRD and a PRD: who your market is, what they’ll pay, and what to
            build first.
          </p>
        </div>
        <div>
          <MousePointerClick size={23} />
          <h3>Hands.</h3>
          <p>
            Personas open a real browser, use your site, get confused, and
            leave.
          </p>
        </div>
      </div>
    </section>
  );
}
