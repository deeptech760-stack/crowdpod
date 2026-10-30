"use client";
import { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { ArrowDown, Play, Sparkles } from "lucide-react";
import { Button, Paper, Waveform } from "./UI";
const thoughts = [
  "Show me the\nprice first…",
  "How much data\ndoes it use?",
  "Have my assistant\nlook at it…",
  "Is there a\nfree tier?",
  "If it syncs with my\ncalendar, take my money…",
];
export default function Hero({ onStart }: { onStart: () => void }) {
  const ref = useRef<HTMLElement>(null);
  const [replay, setReplay] = useState(0);
  useEffect(() => {
    const mm = gsap.matchMedia();
    mm.add("(prefers-reduced-motion: no-preference)", () => {
      const ctx = gsap.context(() => {
        const tl = gsap.timeline({ defaults: { ease: "power3.out" } });
        tl.from(
          ".hero-copy > *",
          { y: 26, opacity: 0, stagger: 0.13, duration: 0.8 },
          0.15,
        )
          .from(
            ".thought",
            { scale: 0.86, opacity: 0, y: 20, stagger: 0.11, duration: 0.65 },
            0.9,
          )
          .from(".hero-path", { strokeDashoffset: 1800, duration: 1.7 }, 1.25)
          .from(".hero-wave", { scale: 0.7, opacity: 0, duration: 0.7 }, 1.5)
          .from(
            ".hero-document",
            { y: 65, rotate: 12, opacity: 0, duration: 1.2 },
            1.7,
          );
        gsap.to(".hero-copy", {
          y: -70,
          opacity: 0.3,
          scrollTrigger: {
            trigger: ref.current,
            start: "top top",
            end: "bottom top",
            scrub: 1,
          },
        });
        gsap.to(".hero-document", {
          y: -95,
          rotate: -3,
          scrollTrigger: {
            trigger: ref.current,
            start: "top top",
            end: "bottom top",
            scrub: 1,
          },
        });
        gsap.utils
          .toArray<HTMLElement>(".thought")
          .forEach((el, i) =>
            gsap.to(el, {
              y: -30 - i * 12,
              scrollTrigger: {
                trigger: ref.current,
                start: "top top",
                end: "bottom top",
                scrub: 1,
              },
            }),
          );
      }, ref);
      return () => ctx.revert();
    });
    return () => mm.revert();
  }, [replay]);
  return (
    <section className="hero" id="home" ref={ref}>
      <div className="hero-copy">
        <p className="hero-eyebrow">A THOUSAND HONEST OPINIONS, BEFORE YOU BUILD</p>
        <h1>
          Before you build,
          <br />
          <em>ask the crowd.</em>
        </h1>
        <p className="hero-description">
          A crowd of AI personas judges your idea, an architect writes
          <br className="desktop-break" /> your BRD and PRD, and hands click through
          your site — honestly.
        </p>
        <div className="hero-actions">
          <Button onClick={onStart}>Test your idea</Button>
          <a className="text-link" href="#how-it-works">
            <Play size={12} fill="currentColor" />
            See how it works
          </a>
        </div>
        <p className="hero-micro">
          Describe your idea in plain text. Get a verdict your team can act on.
        </p>
      </div>
      <div className="hero-art">
        <svg
          className="hero-connector"
          viewBox="0 0 1440 460"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <defs>
            <marker
              id="arrow"
              markerWidth="8"
              markerHeight="8"
              refX="6"
              refY="3"
              orient="auto"
            >
              <path d="M0 0L7 3L0 6Z" fill="#103f36" />
            </marker>
          </defs>
          <path
            className="hero-path"
            d="M-50 90 C170 -40 130 290 285 267 S375 350 460 338 S570 400 650 355 S850 400 965 315 S1035 250 1095 238"
            fill="none"
            stroke="#103f36"
            strokeWidth="1.6"
            strokeDasharray="1800"
            markerEnd="url(#arrow)"
          />
        </svg>
        <div className="thoughts">
          {thoughts.map((t, i) => (
            <div key={t} className={`thought thought-${i}`}>
              <span
                className="thought-float"
                style={{ animationDelay: `-${i * 1.7}s` }}
              >
                {i === 0 && <span className="doodle">╲│╱</span>}
                {t}
                {i === 4 && <Sparkles className="thought-spark" size={20} />}
              </span>
            </div>
          ))}
        </div>
        <button
          className="hero-wave"
          onClick={() => setReplay((n) => n + 1)}
          aria-label="Replay crowd to report animation"
        >
          <Waveform />
        </button>
        <div className="hero-document">
          <Paper />
        </div>
      </div>
      <div className="hero-bottom">
        <span>
          <span className="status-dot" /> PEOPLE WHO CAN’T LIE TO BE NICE
        </span>
        <a href="#idea-story" aria-label="Scroll to discover">
          <ArrowDown size={16} />
        </a>
        <span>A CROWD. AN ARCHITECT. HANDS.</span>
      </div>
    </section>
  );
}
