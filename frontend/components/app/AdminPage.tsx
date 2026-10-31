"use client";
import { useCallback, useEffect, useState } from "react";
import { Ban, Check, Mail, RefreshCw, ShieldAlert, Undo2, X } from "lucide-react";
import { Eyebrow } from "../landing/UI";
import { api, type AdminOverview, type AdminUser, type AuditEvent } from "@/lib/api";

const when = (s: number | null) => (s ? new Date(s * 1000).toLocaleString() : "—");

export default function AdminPage() {
  const [data, setData] = useState<AdminOverview | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [filter, setFilter] = useState<{ user?: AdminUser; alertsOnly: boolean }>({ alertsOnly: true });
  const [error, setError] = useState("");
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);

  const load = useCallback(() => {
    Promise.all([
      api.adminOverview(),
      api.adminEvents({ ...(filter.user ? { user_id: filter.user.id } : {}), ...(filter.alertsOnly ? { only: "alerts" } : {}) }),
    ])
      .then(([o, e]) => {
        setData(o);
        setEvents(e);
        setError("");
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [filter]);

  useEffect(() => {
    load();
    const id = setInterval(load, 15000); // new sign-ins and alerts show up without reloading
    return () => clearInterval(id);
  }, [load]);

  const block = async (u: AdminUser) => {
    const reason = window.prompt(`Block ${u.email}? Their sessions end and their tokens stop working.\n\nReason (kept in the log):`);
    if (reason === null) return;
    try {
      await api.block(u.id, reason);
      setNote({ ok: true, text: `${u.email} is blocked.` });
    } catch (e) {
      setNote({ ok: false, text: e instanceof Error ? e.message : String(e) });
    }
    load();
  };
  const unblock = async (u: AdminUser) => {
    await api.unblock(u.id).catch(() => {});
    setNote({ ok: true, text: `${u.email} can sign in again.` });
    load();
  };
  const testAlert = async () => {
    try {
      const r = await api.testAlert();
      setNote({ ok: r.sent, text: r.sent ? `Test email sent to ${r.to.join(", ")}.` : r.detail });
    } catch (e) {
      setNote({ ok: false, text: e instanceof Error ? e.message : String(e) });
    }
  };

  if (error) {
    return (
      <div className="settings">
        <section className="app-card">
          <Eyebrow>ADMIN</Eyebrow>
          <h1>Administrators only</h1>
          <p className="form-error" role="alert">
            {error}
          </p>
        </section>
      </div>
    );
  }
  if (!data) return <p className="app-empty">Loading the console…</p>;

  return (
    <div className="admin">
      <section className="app-card">
        <Eyebrow>ADMIN</Eyebrow>
        <h1>
          Who is using <em>your site.</em>
        </h1>
        <div className="stat-row">
          <div className="stat">
            <strong>{data.stats.users}</strong>
            <small>accounts</small>
          </div>
          <div className="stat">
            <strong>{data.stats.signed_in_24h}</strong>
            <small>signed in today</small>
          </div>
          <div className="stat">
            <strong>{data.stats.runs_24h}</strong>
            <small>simulations today</small>
          </div>
          <div className="stat">
            <strong>{data.stats.warnings_24h}</strong>
            <small>security warnings today</small>
          </div>
        </div>
        <p className="mcp-hint">
          <Mail size={13} />{" "}
          {data.email_alerts ? (
            <>Serious events are emailed to {data.alert_to.join(", ") || "nobody (set CROWDPOD_ADMIN_EMAILS)"}.</>
          ) : (
            <>Email alerts are off: set CROWDPOD_SMTP_HOST and the other SMTP settings (see SECURITY.md).</>
          )}{" "}
          <button className="text-link small-link" onClick={testAlert}>
            Send a test email
          </button>
        </p>
        {note && (
          <p className={`test-result ${note.ok ? "ok" : "bad"}`} role="status">
            {note.ok ? <Check size={15} /> : <X size={15} />} {note.text}
          </p>
        )}
      </section>

      <section className="app-card">
        <span className="mini-label">ACCOUNTS</span>
        <div className="table-wrap">
          <table className="segment-table admin-table">
            <thead>
              <tr>
                <th>Account</th>
                <th>Sign-in</th>
                <th>Last seen</th>
                <th>Runs</th>
                <th>Warnings (7 days)</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.users.map((u) => (
                <tr key={u.id} className={u.blocked ? "blocked" : u.warnings ? "flagged" : ""}>
                  <th>
                    {u.email}
                    {u.admin && <span className="tag">admin</span>}
                    {u.you && <span className="tag">you</span>}
                    {u.blocked && <span className="tag danger">blocked</span>}
                    <small>
                      {u.name} · joined {when(u.created_at)}
                      {u.blocked_reason ? ` · ${u.blocked_reason}` : ""}
                    </small>
                  </th>
                  <td>{u.google ? "Google" : "Password"}</td>
                  <td>
                    {when(u.last_login)}
                    <small className="muted-line">{u.last_ip ?? ""}</small>
                  </td>
                  <td>{u.runs}</td>
                  <td>
                    <button className="text-link small-link" onClick={() => setFilter({ user: u, alertsOnly: false })}>
                      {u.warnings ? <b className="warn">{u.warnings}</b> : 0} · activity
                    </button>
                  </td>
                  <td>
                    {!u.admin && !u.you &&
                      (u.blocked ? (
                        <button className="chip small" onClick={() => unblock(u)}>
                          <Undo2 size={13} /> Unblock
                        </button>
                      ) : (
                        <button className="chip small danger" onClick={() => block(u)}>
                          <Ban size={13} /> Block
                        </button>
                      ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="app-card">
        <span className="mini-label">
          <ShieldAlert size={13} /> {filter.user ? `ACTIVITY OF ${filter.user.email.toUpperCase()}` : "SECURITY LOG"}
        </span>
        <div className="chip-row">
          <button
            className={`chip small ${!filter.user && filter.alertsOnly ? "on" : ""}`}
            onClick={() => setFilter({ alertsOnly: true })}
          >
            Warnings only
          </button>
          <button
            className={`chip small ${!filter.user && !filter.alertsOnly ? "on" : ""}`}
            onClick={() => setFilter({ alertsOnly: false })}
          >
            Everything (sign-ins too)
          </button>
          {filter.user && <button className="chip small on">{filter.user.email} ✕</button>}
          <button className="chip small" onClick={load} aria-label="Refresh">
            <RefreshCw size={13} />
          </button>
        </div>
        {events.length === 0 ? (
          <p className="app-empty">Nothing here yet.</p>
        ) : (
          <div className="table-wrap">
            <table className="segment-table admin-table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>What</th>
                  <th>Who</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {events.map((e) => (
                  <tr key={e.id} className={`sev-${e.severity}`}>
                    <td>{when(e.at)}</td>
                    <td>
                      <span className={`status-pill sev-${e.severity}`}>{e.severity}</span> {e.label}
                    </td>
                    <td>
                      {e.email || "—"}
                      <small className="muted-line">{e.ip}</small>
                    </td>
                    <td className="detail">{e.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
