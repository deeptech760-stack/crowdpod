"use client";
import { useState } from "react";
import {
  ArrowDown,
  ArrowUpRight,
  Globe,
  MousePointerClick,
  TextCursorInput,
  UsersRound,
} from "lucide-react";
import { AnimatedSample, DemoLabel, Eyebrow } from "./UI";
const methods = [
  {
    title: "Describe your idea.",
    sub: "A few honest sentences.",
    icon: TextCursorInput,
  },
  { title: "Pick your crowd.", sub: "Or let us mix it.", icon: UsersRound },
  {
    title: "Point at your site.",
    sub: "Hands will click through it.",
    icon: MousePointerClick,
  },
  {
    title: "Point at a competitor.",
    sub: "Watch their users get lost.",
    icon: Globe,
  },
];
const crowd = [
  "Mother",
  "Corporate worker",
  "Auto driver",
  "CEO",
  "Athlete",
  "Dancer",
  "Househusband",
  "College student",
];
export default function InputMethods() {
  const [active, setActive] = useState(0);
  const [text, setText] = useState(
    "A subscription app that plans a week of home-cooked meals and orders the groceries.",
  );
  return (
    <section className="section inputs-section" id="inputs">
      <div className="section-heading" data-reveal>
        <div>
          <Eyebrow>FOUR INPUTS. ONE HONEST VERDICT.</Eyebrow>
          <h2>
            Bring the idea.
            <br />
            <em>We’ll bring the crowd.</em>
          </h2>
        </div>
        <p>
          A rough pitch is enough. Add a link and the crowd
          <br />
          will actually use your site, not just talk about it.
        </p>
      </div>
      <div className="input-layout" data-reveal>
        <div
          className="input-options"
          role="tablist"
          aria-label="Inputs"
          aria-orientation="vertical"
        >
          {methods.map(({ title, sub, icon: Icon }, i) => (
            <button
              className={`input-option ${i === active ? "active" : ""}`}
              key={title}
              role="tab"
              id={`input-tab-${i}`}
              aria-selected={i === active}
              aria-controls="input-preview"
              tabIndex={i === active ? 0 : -1}
              onKeyDown={(e) => {
                if (["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) {
                  e.preventDefault();
                  const next =
                    e.key === "Home"
                      ? 0
                      : e.key === "End"
                        ? 3
                        : (active + (e.key === "ArrowDown" ? 1 : 3)) % 4;
                  setActive(next);
                  document.getElementById(`input-tab-${next}`)?.focus();
                }
              }}
              onClick={() => setActive(i)}
            >
              <span className="input-icon">
                <Icon size={21} />
              </span>
              <span>
                <strong>{title}</strong>
                <small>{sub}</small>
              </span>
              <ArrowUpRight size={19} />
            </button>
          ))}
        </div>
        <div
          className={`input-preview input-preview-${active}`}
          role="tabpanel"
          id="input-preview"
          aria-labelledby={`input-tab-${active}`}
        >
          <span className="mini-label">0{active + 1} / THE STARTING POINT</span>
          <AnimatedSample sampleKey={String(active)}>
            {active === 0 ? (
              <div className="text-preview">
                <label htmlFor="rough-idea">YOUR IDEA</label>
                <textarea
                  id="rough-idea"
                  value={text}
                  maxLength={300}
                  onChange={(e) => setText(e.target.value)}
                />
                <ArrowDown size={19} />
                <div className="extracted">
                  <span>WHAT THE CROWD WILL JUDGE</span>
                  <p>{text.trim() || "Start typing to describe your idea."}</p>
                </div>
                <small>
                  Local writing preview. The real run starts from the app.
                </small>
              </div>
            ) : active === 1 ? (
              <div className="chat-preview">
                <p className="chat-ai">Who should judge it?</p>
                <p className="chat-user">{crowd.slice(0, 4).join(" · ")}</p>
                <p className="chat-user">{crowd.slice(4).join(" · ")}</p>
                <p className="chat-ai">
                  Each one gets a budget, a mood and a reason to say no.
                </p>
              </div>
            ) : active === 2 ? (
              <div className="upload-preview">
                <div className="file-stack">
                  <span>CLICK</span>
                  <span>SCROLL</span>
                  <span>LEAVE</span>
                </div>
                <h3>Real browsers. Real confusion.</h3>
                <p>
                  Personas open your landing page, look for what they need,
                  think out loud, and leave when their patience runs out.
                </p>
                <span className="pill">ANY PUBLIC URL</span>
                <small>Illustrative preview. Nothing is opened from here.</small>
              </div>
            ) : (
              <div className="upload-preview">
                <div className="file-stack">
                  <span>YOU</span>
                  <span>THEM</span>
                  <span>DIFF</span>
                </div>
                <h3>Same crowd. Their website.</h3>
                <p>
                  See where their visitors give up, then build the product
                  that doesn’t lose them.
                </p>
                <span className="pill">COMPETITOR MODE</span>
                <small>Illustrative preview. Nothing is opened from here.</small>
              </div>
            )}
          </AnimatedSample>
          <DemoLabel />
        </div>
      </div>
    </section>
  );
}
