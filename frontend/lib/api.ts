// Client for the Crowdpod backend (backend/src/crowdpod/api.py).

export const API_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"
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
  monthly_price: number;
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
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
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
  health: () => call<{ ok: boolean; provider: string; archetypes: number }>("/api/health"),
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
  eventsUrl: (id: string) => `${API_URL}/api/runs/${id}/events`,
  artifactUrl: (id: string, path: string) => `${API_URL}/api/runs/${id}/artifacts/${path}`,
};

export const providerLabel = (p: string) =>
  p === "mock" ? "Offline simulation (rule-based)" : `Model: ${p}`;

export const money = (n: number) => `₹${Math.round(n).toLocaleString("en-IN")}`;
export const pct = (n: number) => `${Math.round(n * 100)}%`;
