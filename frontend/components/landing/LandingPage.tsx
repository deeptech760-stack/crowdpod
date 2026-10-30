"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowUpRight, X } from "lucide-react";
import MotionProvider from "../animations/MotionProvider";
import Navbar from "./Navbar";
import Hero from "./Hero";
import ScatteredIdeas from "./ScatteredIdeas";
import InputMethods from "./InputMethods";
import TransformationStory from "./TransformationStory";
import Intelligence from "./Intelligence";
import BeforeAfter from "./BeforeAfter";
import UseCases from "./UseCases";
import FinalCTA from "./FinalCTA";
import { Logo } from "./UI";
const info: Record<string, { title: string; body: string }> = {
  Privacy: {
    title: "Your idea stays on your server.",
    body: "Crowdpod is self-hosted. Ideas you test are stored in your own Crowdpod database. If you connect a hosted model, the idea text and persona prompts are sent to that model provider. The demos on this page run in your browser only.",
  },
  Terms: {
    title: "A simulation, not a survey.",
    body: "Crowdpod simulates people with AI personas. Its numbers show where to look, not what real customers will do. Confirm every finding by talking to real people before you build or spend on it.",
  },
  Contact: {
    title: "Let’s keep the conversation going.",
    body: "A public contact channel has not been announced yet. In the meantime, explore the interactive story or start a simulation of your own idea.",
  },
};

export default function LandingPage() {
  const router = useRouter();
  const [modal, setModal] = useState<string | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (modal) dialog.current?.showModal();
    else dialog.current?.close();
  }, [modal]);
  const start = () => {
    router.push("/login");
  };
  return (
    <MotionProvider>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <div className="scroll-progress" />
      <Navbar onStart={start} />
      <main id="main">
        <Hero onStart={start} />
        <ScatteredIdeas />
        <InputMethods />
        <TransformationStory />
        <Intelligence />
        <BeforeAfter />
        <UseCases />
        <FinalCTA onStart={start} onInfo={setModal} />
      </main>
      <dialog
        ref={dialog}
        className="preview-dialog"
        onCancel={() => setModal(null)}
        onClick={(e) => {
          if (e.target === e.currentTarget) setModal(null);
        }}
      >
        <button
          className="dialog-close"
          aria-label="Close dialog"
          onClick={() => setModal(null)}
        >
          <X size={22} />
        </button>
        <Logo />
        <span className="mini-label">
          {modal === "start" ? "READY WHEN YOU ARE" : modal}
        </span>
        <h2>
          {modal === "start"
            ? "Stop assuming. Ask the crowd."
            : modal
              ? info[modal]?.title
              : ""}
        </h2>
        <p>
          {modal === "start"
            ? "Describe your idea in a few sentences and a crowd of AI personas will judge it."
            : modal
              ? info[modal]?.body
              : ""}
        </p>
        {(modal === "start" || modal === "Contact") && (
          <a className="button" href="/app/">
            Start a simulation <ArrowUpRight size={17} />
          </a>
        )}
        <button
          className="text-link"
          onClick={() => {
            setModal(null);
            document
              .getElementById("how-it-works")
              ?.scrollIntoView({
                behavior: window.matchMedia("(prefers-reduced-motion: reduce)")
                  .matches
                  ? "instant"
                  : "smooth",
              });
          }}
        >
          Explore the interactive story
        </button>
      </dialog>
    </MotionProvider>
  );
}
