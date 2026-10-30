"use client";
import { Button, Eyebrow, Logo, Paper } from "./UI";
import { navLinks } from "./Navbar";
export default function FinalCTA({
  onStart,
  onInfo,
}: {
  onStart: () => void;
  onInfo: (kind: string) => void;
}) {
  return (
    <>
      <section className="final-cta">
        <div className="final-ghost" aria-hidden="true">
          <Paper />
        </div>
        <div className="final-content" data-reveal>
          <Eyebrow light>STOP ASSUMING</Eyebrow>
          <h2>
            Your friends will say it’s fire.
            <br />
            Your mom will say it’s great.
            <br />
            <em>Ask the crowd.</em>
          </h2>
          <Button light onClick={onStart}>
            Test your idea
          </Button>
          <p>A crowd. An architect. Hands.</p>
        </div>
        <span className="final-fragment final-fragment-one" aria-hidden="true">
          “Bro… it’s fire.”
        </span>
        <span className="final-fragment final-fragment-two" aria-hidden="true">
          “Show me the price.”
        </span>
      </section>
      <footer className="section footer">
        <div className="footer-main">
          <div>
            <a href="#home" aria-label="Crowdpod home">
              <Logo />
            </a>
            <p>Never assume again.</p>
          </div>
          <div className="footer-links">
            {navLinks.slice(0, 3).map(([label, href]) => (
              <a href={href} key={href}>
                {label}
              </a>
            ))}
            <button onClick={onStart}>Get started</button>
          </div>
        </div>
        <div className="footer-bottom">
          <span>Simulated crowds. Confirm with real people.</span>
          <div>
            {["Privacy", "Terms", "Contact"].map((label) => (
              <button key={label} onClick={() => onInfo(label)}>
                {label}
              </button>
            ))}
          </div>
          <span>Crowdpod · Product preview</span>
        </div>
      </footer>
    </>
  );
}
