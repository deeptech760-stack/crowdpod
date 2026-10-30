"use client";
import { useEffect, useRef } from "react";
import gsap from "gsap";
import { MessageSquare, Heart, UsersRound } from "lucide-react";
import { Eyebrow } from "./UI";
const fragments = [
  "Bro… it’s fire.",
  "Looks great, beta!",
  "Everyone would use this.",
  "I’d totally pay for it.",
  "Send me the link later…",
];
export default function ScatteredIdeas() {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const mm = gsap.matchMedia();
    mm.add(
      "(min-width: 900px) and (prefers-reduced-motion: no-preference)",
      () => {
        const ctx = gsap.context(() => {
          const tl = gsap.timeline({
            scrollTrigger: {
              trigger: ref.current,
              start: "top 15%",
              end: "+=650",
              pin: true,
              scrub: 1,
            },
          });
          gsap.utils
            .toArray<HTMLElement>(".fragment")
            .forEach((el, i) =>
              tl.to(
                el,
                {
                  x: 0,
                  y: (i - 2) * 16,
                  rotate: 0,
                  opacity: 0.12,
                  duration: 1,
                },
                0,
              ),
            );
          tl.fromTo(
            ".organized-thought",
            { opacity: 0, scale: 0.85 },
            { opacity: 1, scale: 1, duration: 0.6 },
            0.6,
          );
        }, ref);
        return () => ctx.revert();
      },
    );
    return () => mm.revert();
  }, []);
  return (
    <section className="ideas-section section" id="idea-story" ref={ref}>
      <div className="ideas-copy" data-reveal>
        <Eyebrow>YOUR BRAIN IS A TERRIBLE FOCUS GROUP</Eyebrow>
        <h2>
          Your friends
          <br />
          are <em>lying to you.</em>
        </h2>
        <p>
          Your mom says it’s great. Your friends say it’s fire.
          <br />
          Then nobody uses it. Kind words aren’t data.
        </p>
        <span className="quiet-caption">ONE PERSON IS NOISE. A CROWD IS SIGNAL.</span>
      </div>
      <div className="fragment-stage">
        {fragments.map((t, i) => (
          <div className={`fragment fragment-${i}`} key={t}>
            {i % 2 ? <Heart size={15} /> : <MessageSquare size={15} />}
            <span>{t}</span>
          </div>
        ))}
        <div className="organized-thought">
          <UsersRound size={30} />
          <span>
            A crowd that can’t
            <br />
            lie to be nice.
          </span>
        </div>
      </div>
    </section>
  );
}
