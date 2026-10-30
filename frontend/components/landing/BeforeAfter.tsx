"use client";
import { useState } from "react";
import { ChevronsLeftRight, FileText } from "lucide-react";
import { Eyebrow } from "./UI";
export default function BeforeAfter() {
  const [split, setSplit] = useState(48);
  return (
    <section className="comparison-section">
      <div className="section">
        <div className="center-heading" data-reveal>
          <Eyebrow>SAME IDEA. HONEST FEEDBACK.</Eyebrow>
          <h2>
            Less flattery. <em>More signal.</em>
          </h2>
          <p>Move the handle. Compare your group chat with a crowd.</p>
        </div>
        <div className="comparison" data-reveal>
          <div className="comparison-after">
            <div className="comparison-paper">
              <span className="mini-label">AFTER · THE CROWD’S VERDICT</span>
              <h3>
                <FileText size={25} /> Crowd report
              </h3>
              <dl>
                <dt>Your real market</dt>
                <dd>Working parents, not the students you assumed.</dd>
                <dt>Willingness to pay</dt>
                <dd>Median ₹220 a month against your ₹249 price.</dd>
                <dt>Top objection</dt>
                <dd>“I couldn’t find the price.” — said by 212 people.</dd>
                <dt>Build first</dt>
                <dd>A weekly plan in under five minutes.</dd>
                <dt>Ask real people next</dt>
                <dd>
                  How do you plan dinners today, and what does it cost you?
                </dd>
              </dl>
            </div>
          </div>
          <div
            className="comparison-before"
            style={{ clipPath: `inset(0 ${100 - split}% 0 0)` }}
          >
            <div className="messy-paper">
              <span className="mini-label">BEFORE · YOUR GROUP CHAT</span>
              <h3>What my friends said…</h3>
              <p>bro it’s fire!!</p>
              <p className="scribble-note">mom: looks great beta!</p>
              <p>→ everyone would use this</p>
              <p className="crossed">I’ll check it out later</p>
              <p className="scribble-note">who is it for though?</p>
              <p>Nobody signed up.</p>
            </div>
          </div>
          <div className="comparison-divider" style={{ left: `${split}%` }}>
            <span>
              <ChevronsLeftRight size={23} />
            </span>
          </div>
          <input
            className="comparison-range"
            type="range"
            min="0"
            max="100"
            value={split}
            onChange={(e) => setSplit(Number(e.target.value))}
            aria-label="Before and after comparison"
            aria-valuetext={`${split}% friends' feedback, ${100 - split}% crowd report`}
          />
        </div>
        <div className="comparison-captions">
          <span>WHAT YOUR FRIENDS SAY</span>
          <span>WHAT THE CROWD SAYS</span>
        </div>
      </div>
    </section>
  );
}
