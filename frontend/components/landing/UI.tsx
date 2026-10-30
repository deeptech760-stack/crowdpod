"use client";
import { useRef, type CSSProperties, type ReactNode } from "react";
import { motion, useReducedMotion } from "motion/react";
import {
  ArrowUpRight,
  ChartNoAxesColumnIncreasing,
  FileText,
  ListChecks,
  Target,
  Users,
  UsersRound,
} from "lucide-react";
export function Logo() {
  return (
    <span className="logo">
      <span className="logo-icon">
        <UsersRound size={24} />
        <Users size={15} />
      </span>
      <span>
        Crowd<span className="logo-brd">pod</span>
      </span>
    </span>
  );
}
export function Button({
  children,
  onClick,
  light = false,
}: {
  children: ReactNode;
  onClick: () => void;
  light?: boolean;
}) {
  const ref = useRef<HTMLButtonElement>(null);
  const reduced = useReducedMotion();
  return (
    <button
      ref={ref}
      className={`button ${light ? "button-light" : ""}`}
      onClick={onClick}
      onPointerMove={(e) => {
        if (reduced || e.pointerType !== "mouse") return;
        const r = e.currentTarget.getBoundingClientRect();
        ref.current!.style.translate = `${(e.clientX - r.left - r.width / 2) * 0.07}px ${(e.clientY - r.top - r.height / 2) * 0.1}px`;
      }}
      onPointerLeave={() => {
        if (ref.current) ref.current.style.translate = "0 0";
      }}
    >
      {children}
      <ArrowUpRight size={17} />
    </button>
  );
}
export function Eyebrow({
  children,
  light = false,
}: {
  children: ReactNode;
  light?: boolean;
}) {
  return (
    <p className={`eyebrow ${light ? "light" : ""}`}>
      <span />
      {children}
    </p>
  );
}
export function Waveform({ compact = false }: { compact?: boolean }) {
  return (
    <span className={`waveform ${compact ? "compact" : ""}`} aria-hidden="true">
      {Array.from({ length: 37 }, (_, i) => (
        <i
          key={i}
          style={
            {
              "--bar-height": `${(10 + Math.abs(Math.sin(i * 0.72) * Math.cos(i * 0.24)) * 36).toFixed(2)}px`,
              "--delay": `${(-i * 0.13).toFixed(2)}s`,
            } as CSSProperties
          }
        />
      ))}
    </span>
  );
}
const sections = [
  {
    icon: FileText,
    title: "Your real market",
    text: "Tired office workers, not students.",
  },
  {
    icon: Target,
    title: "What they’ll pay",
    text: "A median of ₹220 a month.",
  },
  {
    icon: ListChecks,
    title: "Build first",
    text: "Calendar sync · Price upfront",
  },
  {
    icon: ChartNoAxesColumnIncreasing,
    title: "Why they leave",
    text: "They couldn’t find the price.",
  },
];
export function Paper({
  detailed = false,
  className = "",
}: {
  detailed?: boolean;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();
  return (
    <div
      className={`paper-wrap ${className}`}
      onPointerMove={(e) => {
        if (reduced || e.pointerType !== "mouse" || !ref.current) return;
        const r = e.currentTarget.getBoundingClientRect();
        ref.current.style.transform = `perspective(900px) rotateX(${-(e.clientY - r.top - r.height / 2) / 70}deg) rotateY(${(e.clientX - r.left - r.width / 2) / 70}deg)`;
      }}
      onPointerLeave={() => {
        if (ref.current) ref.current.style.transform = "";
      }}
    >
      <div className="paper-back" />
      <article ref={ref} className="paper">
        <div className="paper-top">
          <FileText size={19} />
          <span>
            CROWDPOD
            <br />
            RUN / 001
          </span>
        </div>
        <h3>
          Crowd Report
          <br />
          BRD + PRD
        </h3>
        <div className="paper-subtitle">1,000 PEOPLE · ONE VERDICT</div>
        {sections.map(({ icon: Icon, title, text }) => (
          <div className="paper-section" key={title}>
            <Icon size={17} />
            <div>
              <h4>{title}</h4>
              {detailed ? (
                <p>{text}</p>
              ) : (
                <>
                  <span className="ink-line" />
                  <span className="ink-line short" />
                  {title === "Build first" && (
                    <span className="ink-line medium" />
                  )}
                </>
              )}
            </div>
          </div>
        ))}
        <div className="paper-footer">
          <span>STOP ASSUMING. ASK THE CROWD.</span>
          <span>01</span>
        </div>
      </article>
    </div>
  );
}
export function AnimatedSample({
  children,
  sampleKey,
}: {
  children: ReactNode;
  sampleKey: string;
}) {
  return (
    <motion.div
      key={sampleKey}
      initial={{ opacity: 0.4, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
    >
      {children}
    </motion.div>
  );
}
export function DemoLabel() {
  return (
    <span className="demo-label">
      <Users size={12} /> Interactive example · not a live simulation
    </span>
  );
}
