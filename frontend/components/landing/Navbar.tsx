"use client";
import { useEffect, useState } from "react";
import { Menu, X } from "lucide-react";
import { Button, Logo } from "./UI";
export const navLinks = [
  ["How it works", "#how-it-works"],
  ["The architect", "#features"],
  ["Use cases", "#use-cases"],
  ["Why it works", "#for-teams"],
];
export default function Navbar({ onStart }: { onStart: () => void }) {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const update = () => setScrolled(window.scrollY > 40);
    window.addEventListener("scroll", update, { passive: true });
    update();
    return () => window.removeEventListener("scroll", update);
  }, []);
  return (
    <header className={`nav-shell ${scrolled ? "is-scrolled" : ""}`}>
      <nav className="navbar" aria-label="Main navigation">
        <a href="#home" aria-label="Crowdpod home">
          <Logo />
        </a>
        <div className="nav-links">
          {navLinks.map(([label, href]) => (
            <a href={href} key={href}>
              {label}
            </a>
          ))}
        </div>
        <div className="nav-actions">
          <Button onClick={onStart}>Get started</Button>
          <button
            className="menu-toggle"
            aria-label={open ? "Close navigation" : "Open navigation"}
            aria-expanded={open}
            aria-controls="mobile-nav"
            onClick={() => setOpen(!open)}
          >
            {open ? <X /> : <Menu />}
          </button>
        </div>
      </nav>
      {open && (
        <div
          id="mobile-nav"
          className="mobile-nav"
          onKeyDown={(e) => {
            if (e.key === "Escape") setOpen(false);
          }}
        >
          {navLinks.map(([label, href]) => (
            <a href={href} key={href} onClick={() => setOpen(false)}>
              {label}
            </a>
          ))}
        </div>
      )}
    </header>
  );
}
