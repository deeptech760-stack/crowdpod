"use client";
import { useState } from "react";
import {
  ArrowUpRight,
  Check,
  Lightbulb,
  Users,
  Search,
  BriefcaseBusiness,
  GraduationCap,
} from "lucide-react";
import { AnimatedSample, Eyebrow } from "./UI";
const cases = [
  {
    name: "Founders",
    icon: Lightbulb,
    title: "Find your market\nbefore you raise.",
    copy: "Learn who actually wants your product and what they would pay, before you spend months building it.",
    artifact: "The market check",
    items: [
      "The segment that says yes",
      "A price they accept",
      "The first feature to build",
    ],
  },
  {
    name: "Product managers",
    icon: Users,
    title: "Test the feature\nbefore the sprint.",
    copy: "Run a change past the crowd and see which segments it wins or loses, before engineering starts.",
    artifact: "The feature check",
    items: [
      "Who it helps",
      "Who it confuses",
      "What to cut",
    ],
  },
  {
    name: "Competitor research",
    icon: Search,
    title: "Watch their users\nget lost.",
    copy: "Point the same crowd at a competitor’s site and see exactly where their visitors give up.",
    artifact: "The competitor teardown",
    items: [
      "Where visitors stall",
      "What they never find",
      "The gap you can own",
    ],
  },
  {
    name: "Agencies & consultants",
    icon: BriefcaseBusiness,
    title: "Evidence for\nthe client pitch.",
    copy: "Show a client how their audience reacts to a concept before anyone signs off on the build.",
    artifact: "The concept test",
    items: ["Audience reactions", "Price signals", "A ranked shortlist"],
  },
  {
    name: "Students & builders",
    icon: GraduationCap,
    title: "Beyond “bro,\nit’s fire.”",
    copy: "Find out whether your hackathon or college project has users beyond your friends, and what they want.",
    artifact: "The project reality check",
    items: ["Who would use it", "What they’d pay", "What to build next"],
  },
];
export default function UseCases() {
  const [active, setActive] = useState(0);
  const current = cases[active];
  const Icon = current.icon;
  return (
    <section className="section use-cases" id="use-cases">
      <div className="section-heading" data-reveal>
        <div>
          <Eyebrow>FOR ANYONE WHO HAS STOPPED ASSUMING</Eyebrow>
          <h2>
            From a hunch
            <br />
            to <em>evidence.</em>
          </h2>
        </div>
      </div>
      <div className="use-tabs" aria-label="Use cases">
        {cases.map((c, i) => (
          <button
            key={c.name}
            onClick={() => setActive(i)}
            aria-pressed={i === active}
            className={i === active ? "active" : ""}
          >
            {c.name}
          </button>
        ))}
      </div>
      <div className="use-panel" data-reveal>
        <AnimatedSample sampleKey={current.name}>
          <div className="use-copy">
            <span className="use-case-icon">
              <Icon size={24} />
            </span>
            <h3>{current.title}</h3>
            <p>{current.copy}</p>
            <a className="text-link" href="#how-it-works">
              See the crowd decide <ArrowUpRight size={16} />
            </a>
          </div>
        </AnimatedSample>
        <div className="use-art">
          <div className="use-art-orbit" />
          <div className="use-art-paper">
            <span className="mini-label">WHAT YOU GET</span>
            <AnimatedSample sampleKey={current.artifact}>
              <h4>{current.artifact}</h4>
              {current.items.map((item, i) => (
                <p key={item}>
                  <span>0{i + 1}</span>
                  {item}
                  <Check size={15} />
                </p>
              ))}
            </AnimatedSample>
            <span className="paper-stamp">NO MORE ASSUMING.</span>
          </div>
          <span className="spark-label">It starts with “would anyone…”</span>
        </div>
      </div>
      <div className="teams-note" id="for-teams" data-reveal>
        <Users size={24} />
        <h3>
          A thousand perspectives.
          <br />
          <em>One honest verdict.</em>
        </h3>
        <p>
          It won’t replace talking to real people.
          <br />
          It tells you which people to talk to first,
          <br />
          and what to ask them.
        </p>
      </div>
    </section>
  );
}
