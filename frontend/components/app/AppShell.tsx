"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { LogOut, Plus, Settings, ShieldCheck } from "lucide-react";
import { Logo } from "../landing/UI";
import { API_URL, api, providerLabel, type AuthUser } from "@/lib/api";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [provider, setProvider] = useState<string | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [ready, setReady] = useState(false);
  const [down, setDown] = useState(false);

  useEffect(() => {
    api
      .me()
      .then((m) => {
        if (m.required && !m.user) {
          // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- auth boundary: full page load to the sign-in page
          window.location.assign(`/login/?next=${encodeURIComponent(window.location.pathname + window.location.search)}`);
          return;
        }
        setUser(m.user);
        setReady(true);
        return api.health().then((h) => setProvider(h.provider ?? null));
      })
      .catch(() => {
        setDown(true);
        setReady(true);
      });
  }, []);

  const signOut = async () => {
    await api.logout().catch(() => {});
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- auth boundary: full page load so nothing from the session stays in memory
    window.location.assign("/login/");
  };

  return (
    <div className="app-root">
      <header className="app-header">
        <Link href="/" aria-label="Crowdpod home">
          <Logo />
        </Link>
        <div className="app-header-actions">
          {provider && (
            <a
              className={`provider-badge ${provider === "mock" ? "offline" : ""}`}
              href="/app/settings/"
              title="Change the brain in Settings"
            >
              <span className="status-dot" /> {providerLabel(provider)}
            </a>
          )}
          {user?.admin && (
            <a className="app-link" href="/app/admin/">
              <ShieldCheck size={16} /> Admin
            </a>
          )}
          <a className="app-link" href="/app/settings/">
            <Settings size={16} /> Settings
          </a>
          <a className="app-new" href="/app/">
            <Plus size={16} /> New simulation
          </a>
          {user && (
            <button className="app-link" onClick={signOut} title={`Signed in as ${user.email}`}>
              <LogOut size={16} /> Sign out
            </button>
          )}
        </div>
      </header>
      {down && (
        <div className="app-banner" role="alert">
          Can’t reach the Crowdpod server at <code>{API_URL}</code>. Start it with{" "}
          <code>uv run crowdpod serve</code> in <code>backend/</code>, then reload.
        </div>
      )}
      <main className="app-main">{ready ? children : <p className="app-empty">Checking your sign-in…</p>}</main>
    </div>
  );
}
