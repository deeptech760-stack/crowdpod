"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { Logo } from "../landing/UI";
import { API_URL, api, providerLabel } from "@/lib/api";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [provider, setProvider] = useState<string | null>(null);
  const [down, setDown] = useState(false);
  useEffect(() => {
    api
      .health()
      .then((h) => setProvider(h.provider))
      .catch(() => setDown(true));
  }, []);
  return (
    <div className="app-root">
      <header className="app-header">
        <Link href="/" aria-label="Crowdpod home">
          <Logo />
        </Link>
        <div className="app-header-actions">
          {provider && (
            <span className={`provider-badge ${provider === "mock" ? "offline" : ""}`}>
              <span className="status-dot" /> {providerLabel(provider)}
            </span>
          )}
          <a className="app-new" href="/app/">
            <Plus size={16} /> New simulation
          </a>
        </div>
      </header>
      {down && (
        <div className="app-banner" role="alert">
          Can’t reach the Crowdpod server at <code>{API_URL}</code>. Start it with{" "}
          <code>uv run crowdpod serve</code> in <code>backend/</code>, then reload.
        </div>
      )}
      <main className="app-main">{children}</main>
    </div>
  );
}
