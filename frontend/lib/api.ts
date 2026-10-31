// Client for the Crowdpod backend (backend/src/crowdpod/api.py).

// On your own computer the API is on port 8000 of the same host name (localhost or 127.0.0.1), so the
// sign-in cookie counts as same-site. On a hosted site /api/* is proxied by the host (vercel.json),
// so the API is the page's own origin and the cookie never crosses sites.
const LOCAL = /^(localhost|127\.0\.0\.1)$/;
export const API_URL = (
  process.env.NEXT_PUBLIC_API_URL ??
  (typeof window === "undefined"
    ? "http://127.0.0.1:8000"
    : LOCAL.test(window.location.hostname)
      ? `${window.location.protocol}//${window.location.hostname}:8000`
      : "")
).replace(/\/$/, "");

export type Verdict = "adopt" | "maybe" | "reject";
export type PricePeriod = "one_time" | "month" | "year" | "free";

export interface IdeaBrief {
  name: string;
  pitch: string;
  category?: string;
  price: number;
  currency?: string;
  price_period: PricePeriod;
  target_hint?: string;
  url?: string | null;
  competitor_url?: string | null;
}

export interface RunRequest {
  brief: IdeaBrief;
  crowd_size: number;
  mix?: Record<string, number> | null;
  seed?: number;
  audience?: "generated" | "builtin" | "both";
  audience_size?: number;
  context_notes?: string;
  described?: string[]; // people the user describes; each becomes a full persona
  hands?: {
    url: string;
    personas: number;
    max_steps?: number;
    archetypes?: string[];
    goal?: string | null;
    goals?: Record<string, string> | null;
  } | null;
}

export interface Archetype {
  id: string;
  label: string;
  weight: number;
  profession: string;
  interests: string[];
  objections: string[];
  goals_on_site: string[];
}

export interface PersonaLite {
  id: string;
  name: string;
  age: number;
  archetype_id: string;
  mood: string;
}

export interface Reaction {
  persona_id: string;
  verdict: Verdict;
  willingness_to_pay: number;
  sentiment: number;
  quote: string;
  top_objection: string;
  must_have: string;
  reasoning: string;
  provider: string;
}

export interface SegmentStats {
  archetype_id: string;
  label: string;
  count: number;
  adopt: number;
  maybe: number;
  reject: number;
  adoption_rate: number;
  interest_rate: number;
  avg_sentiment: number;
  median_wtp: number;
  price_fit_rate: number;
  score: number;
  top_objections: [string, number][];
  top_must_haves: [string, number][];
}

export interface CrowdSummary {
  size: number;
  monthly_price: number; // the price compared with budgets, in price_unit terms
  price_unit?: "one_time" | "month";
  adoption_rate: number;
  interest_rate: number;
  median_wtp: number;
  median_wtp_interested?: number; // missing on runs saved before it existed
  price_fit_rate: number;
  best_segment: string | null;
  worst_segment: string | null;
  segments: SegmentStats[];
  top_objections: [string, number][];
  top_must_haves: [string, number][];
  headline: string;
}

export interface HandsStep {
  index: number;
  t: number;
  thought: string;
  action: "click" | "type" | "scroll" | "back" | "done" | "give_up";
  target: string;
  target_label: string;
  text: string;
  url: string;
  screenshot: string;
  error: string;
}

export interface HandsSession {
  persona_id: string;
  persona_name: string;
  archetype_id: string;
  url: string;
  goal: string;
  outcome: "success" | "gave_up" | "step_limit" | "error";
  seconds: number;
  summary: string;
  steps: HandsStep[];
}

export interface RunInfo {
  id: string;
  created_at: number;
  status: "queued" | "running" | "finished" | "failed";
  provider: string;
  request: RunRequest;
  error: string | null;
  summary: CrowdSummary | null;
  has_docs: boolean;
}

export interface Research {
  summary: string;
  facts: string[];
  price_points: string[];
  buyer_segments: string[];
  sources: { title: string; url: string }[];
  grounded: boolean;
}

export interface GeneratedPersonaCard {
  id: string;
  label: string;
  share: number;
  profession: string;
  city: string;
  age: [number, number];
  budget_month: [number, number];
  purchase_budget: [number, number];
  objections: string[];
  must_haves: string[];
  evidence: string[];
  note: string;
}

export interface RunListItem {
  id: string;
  created_at: number;
  status: RunInfo["status"];
  provider: string;
  name: string;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    credentials: "include", // send the sign-in cookie
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (res.status === 401 && !path.startsWith("/api/auth/") && typeof window !== "undefined") {
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- auth boundary: a full page load, so no state from the signed-out session survives
    window.location.assign(`/login/?next=${encodeURIComponent(window.location.pathname + window.location.search)}`);
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail)
        detail =
          typeof body.detail === "string"
            ? body.detail
            : body.detail
                .map((d: { loc: string[]; msg: string }) => `${d.loc.slice(1).join(".")}: ${d.msg}`)
                .join("; ");
    } catch {}
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => call<{ ok: boolean; provider?: string; archetypes?: number }>("/api/health"),
  archetypes: () => call<Archetype[]>("/api/archetypes"),
  runs: () => call<RunListItem[]>("/api/runs"),
  run: (id: string) => call<RunInfo>(`/api/runs/${id}`),
  hands: (id: string) => call<HandsSession[]>(`/api/runs/${id}/hands`),
  createRun: (req: RunRequest) =>
    call<{ run_id: string }>("/api/runs", { method: "POST", body: JSON.stringify(req) }),
  interview: (runId: string, personaId: string, question: string) =>
    call<{ answer: string }>(`/api/runs/${runId}/personas/${personaId}/interview`, {
      method: "POST",
      body: JSON.stringify({ question }),
    }),
  authConfig: () => call<{ required: boolean; google: boolean }>("/api/auth/config"),
  me: () => call<{ user: AuthUser | null; required: boolean; mode: "local" | "public" }>("/api/auth/me"),
  login: (email: string, password: string) =>
    call<{ user: AuthUser }>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  register: (name: string, email: string, password: string) =>
    call<{ user: AuthUser }>("/api/auth/register", { method: "POST", body: JSON.stringify({ name, email, password }) }),
  logout: () => call<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),
  googleStartUrl: () => `${API_URL}/api/auth/google/start`,
  eventsUrl: (id: string) => `${API_URL}/api/runs/${id}/events`,
  artifactUrl: (id: string, path: string) => `${API_URL}/api/runs/${id}/artifacts/${path}`,
  settings: () => call<PublicSettings>("/api/settings"),
  saveSettings: (brain: BrainForm, browser: BrowserSettings) =>
    call<PublicSettings>("/api/settings", { method: "PUT", body: JSON.stringify({ brain, browser }) }),
  testBrain: (brain: BrainForm) =>
    call<{ ok: boolean; label: string; ms: number; detail: string }>("/api/settings/test", {
      method: "POST",
      body: JSON.stringify(brain),
    }),
  listModels: (brain: BrainForm) =>
    call<{ models: string[] }>("/api/settings/models", { method: "POST", body: JSON.stringify(brain) }),
  mcpSetup: () => call<McpSetup>("/api/settings/mcp"),
  tokens: () => call<AccessToken[]>("/api/tokens"),
  createToken: (name: string) =>
    call<AccessToken & { token: string }>("/api/tokens", { method: "POST", body: JSON.stringify({ name }) }),
  revokeToken: (id: string) => call<{ ok: boolean }>(`/api/tokens/${id}`, { method: "DELETE" }),
  adminOverview: () => call<AdminOverview>("/api/admin/overview"),
  adminEvents: (opts: { user_id?: string; only?: "alerts" } = {}) =>
    call<AuditEvent[]>(`/api/admin/events?${new URLSearchParams(opts as Record<string, string>)}`),
  block: (userId: string, reason: string) =>
    call<{ ok: boolean }>(`/api/admin/users/${userId}/block`, { method: "POST", body: JSON.stringify({ reason }) }),
  unblock: (userId: string) => call<{ ok: boolean }>(`/api/admin/users/${userId}/unblock`, { method: "POST" }),
  testAlert: () => call<{ sent: boolean; to: string[]; detail: string }>("/api/admin/alerts/test", { method: "POST" }),
};

export interface McpSetup {
  api_url: string;
  needs_token: boolean;
  browsers: string;
  claude_code: string;
  codex: string;
  claude_desktop: string;
  opencode: string;
}

export interface AccessToken {
  id: string;
  name: string;
  created_at: number;
  last_used: number | null;
}

export interface AdminUser {
  id: string;
  email: string;
  name: string;
  google: boolean;
  created_at: number;
  last_login: number | null;
  last_ip: string | null;
  runs: number;
  warnings: number;
  blocked: boolean;
  blocked_reason: string | null;
  admin: boolean;
  you: boolean;
}

export interface AuditEvent {
  id: number;
  at: number;
  user_id: string | null;
  email: string;
  ip: string;
  kind: string;
  label: string;
  severity: "info" | "warning" | "high";
  detail: string;
}

export interface AdminOverview {
  stats: { users: number; signed_in_24h: number; runs_24h: number; warnings_24h: number; blocked: number };
  users: AdminUser[];
  email_alerts: boolean;
  alert_to: string[];
}

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  google: boolean;
  admin?: boolean;
}

export type BrainProvider = "mock" | "anthropic" | "openai";

export interface BrowserSettings {
  show_windows: boolean;
  slow_mo_ms: number;
  parallel: number;
}

/** What the settings form sends. api_key: null keeps the saved key, "" removes it. */
export interface BrainForm {
  provider: BrainProvider;
  base_url: string;
  api_key: string | null;
  model: string;
  concurrency: number;
  batch_size: number;
  effort: "low" | "medium" | "high";
}

/** What the server sends back: never the key itself. */
export interface PublicSettings {
  brain: Omit<BrainForm, "api_key"> & { has_key: boolean; key_hint: string };
  browser: BrowserSettings;
}

export const providerLabel = (p: string) =>
  p === "mock" ? "Offline simulation (rule-based)" : `Brain: ${p}`;

export const money = (n: number) => `₹${Math.round(n).toLocaleString("en-IN")}`;
/** A price or budget in the terms of the run: "₹1,89,900 one-time" or "₹299/mo". */
export const priced = (n: number, unit?: "one_time" | "month") =>
  unit === "one_time" ? `${money(n)} one-time` : `${money(n)}/mo`;
export const pct = (n: number) => `${Math.round(n * 100)}%`;
