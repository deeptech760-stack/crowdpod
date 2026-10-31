"use client";
import { useEffect, useState } from "react";
import { Check, Copy, Cpu, KeyRound, Loader2, MonitorPlay, Plug, PlugZap, Sparkles, Trash2, X } from "lucide-react";
import { Eyebrow } from "../landing/UI";
import {
  api,
  type AccessToken,
  type BrainForm,
  type BrainProvider,
  type BrowserSettings,
  type McpSetup,
  type PublicSettings,
} from "@/lib/api";

const CLAUDE_MODELS = [
  ["claude-opus-5-5", "Claude Opus 5.5 — most capable (recommended)"],
  ["claude-sonnet-5-5", "Claude Sonnet 5.5 — faster"],
  ["claude-haiku-5-5", "Claude Haiku 5.5 — cheapest"],
];

// Any service that speaks the OpenAI Chat Completions format works; these only fill the address.
const PRESETS: [string, string][] = [
  ["OpenAI", "https://api.openai.com/v1"],
  ["OpenRouter", "https://openrouter.ai/api/v1"],
  ["Groq", "https://api.groq.com/openai/v1"],
  ["Together", "https://api.together.xyz/v1"],
  ["LM Studio (this computer)", "http://localhost:1234/v1"],
  ["Ollama (this computer)", "http://localhost:11434/v1"],
];

const BRAINS: { id: BrainProvider; title: string; body: string; icon: typeof Cpu }[] = [
  {
    id: "mock",
    title: "Offline simulation",
    body: "Free and works without internet. Rule-based: it reads ideas by keywords, so use it for rehearsals, not real verdicts.",
    icon: Cpu,
  },
  {
    id: "anthropic",
    title: "Claude",
    body: "Claude models with your own Anthropic API key. Usage is billed to your Anthropic account.",
    icon: Sparkles,
  },
  {
    id: "openai",
    title: "Any OpenAI-compatible model",
    body: "OpenAI, OpenRouter, Groq, Together, or a model running on this computer with LM Studio or Ollama.",
    icon: Plug,
  },
];

type Saved = PublicSettings["brain"];

export default function SettingsPage() {
  const [who, setWho] = useState<{ manage: boolean; signedIn: boolean } | null>(null);
  const [token, setToken] = useState(""); // a token created just now, shown once and filled into the setup
  useEffect(() => {
    api
      .me()
      .then((m) => setWho({ manage: m.mode !== "public" || !!m.user?.admin, signedIn: !!m.user }))
      .catch(() => setWho({ manage: true, signedIn: false }));
  }, []);
  if (!who) return <p className="app-empty">Loading settings…</p>;
  return (
    <div className="settings">
      {who.manage ? (
        <BrainSettings />
      ) : (
        <section className="app-card">
          <Eyebrow>SETTINGS</Eyebrow>
          <h1>
            Connect <em>your own agent.</em>
          </h1>
          <p className="app-lede">
            The model that plays the crowd on this site is chosen by its owner. Create an access token below to run
            Crowdpod from Claude Code, Codex, Claude Desktop or OpenCode on your computer.
          </p>
        </section>
      )}
      {who.signedIn && <TokensSection onCreated={setToken} />}
      <McpSection token={token} />
    </div>
  );
}

function BrainSettings() {
  const [saved, setSaved] = useState<Saved | null>(null);
  const [form, setForm] = useState<Omit<BrainForm, "api_key">>({
    provider: "mock", base_url: "", model: "", concurrency: 4, batch_size: 20, effort: "medium",
  });
  const [keyInput, setKeyInput] = useState("");
  const [removeKey, setRemoveKey] = useState(false);
  const [browser, setBrowser] = useState<BrowserSettings>({ show_windows: false, slow_mo_ms: 0, parallel: 2 });
  const [models, setModels] = useState<string[]>([]);
  const [busy, setBusy] = useState<"" | "test" | "save" | "models">("");
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    api
      .settings()
      .then((s) => {
        setSaved(s.brain);
        const { has_key: _h, key_hint: _k, ...rest } = s.brain; // eslint-disable-line @typescript-eslint/no-unused-vars
        setForm(rest);
        setBrowser(s.browser);
      })
      .catch((e) => setLoadError(e instanceof Error ? e.message : String(e)));
  }, []);

  // The saved key is only reused for the same provider and address (the server enforces this too).
  const keyCarries = !!saved?.has_key && saved.provider === form.provider && saved.base_url === form.base_url.replace(/\/$/, "");
  const brainForm = (): BrainForm => ({
    ...form,
    base_url: form.provider === "anthropic" ? "" : form.base_url.trim(),
    api_key: keyInput ? keyInput : removeKey || !keyCarries ? "" : null,
  });

  const pick = (provider: BrainProvider) => {
    setResult(null);
    setModels([]);
    setForm((f) => ({
      ...f,
      provider,
      base_url: provider === "openai" ? (saved?.provider === "openai" ? saved.base_url : "") : "",
      model:
        provider === "anthropic"
          ? saved?.provider === "anthropic" ? saved.model : "claude-opus-5-5"
          : provider === "openai" ? (saved?.provider === "openai" ? saved.model : "") : "",
    }));
  };

  const run = async (kind: "test" | "save" | "models") => {
    setBusy(kind);
    setResult(null);
    try {
      if (kind === "test") {
        const r = await api.testBrain(brainForm());
        setResult({ ok: r.ok, text: r.detail });
      } else if (kind === "models") {
        const r = await api.listModels(brainForm());
        setModels(r.models);
        setResult({ ok: true, text: `${r.models.length} models available.` });
      } else {
        const s = await api.saveSettings(brainForm(), browser);
        setSaved(s.brain);
        setKeyInput("");
        setRemoveKey(false);
        setResult({ ok: true, text: "Saved. New simulations will use this brain." });
      }
    } catch (e) {
      setResult({ ok: false, text: e instanceof Error ? e.message : String(e) });
    }
    setBusy("");
  };

  const needsKey = form.provider === "anthropic";

  return (
    <>
      <section className="app-card">
        <Eyebrow>SETTINGS</Eyebrow>
        <h1>
          Who does the <em>thinking?</em>
        </h1>
        <p className="app-lede">
          Pick the brain that plays every persona: their verdicts, their thoughts, and every click on a website.
        </p>
        {loadError && (
          <p className="form-error" role="alert">
            {loadError}
          </p>
        )}

        <div className="brain-options" role="radiogroup" aria-label="Brain">
          {BRAINS.map(({ id, title, body, icon: Icon }) => (
            <button
              key={id}
              role="radio"
              aria-checked={form.provider === id}
              className={`brain-option ${form.provider === id ? "on" : ""}`}
              onClick={() => pick(id)}
            >
              <span className="input-icon">
                <Icon size={20} />
              </span>
              <strong>{title}</strong>
              <small>{body}</small>
              {saved?.provider === id && <span className="tag">in use</span>}
            </button>
          ))}
        </div>

        {form.provider !== "mock" && (
          <div className="brain-fields">
            {form.provider === "openai" && (
              <>
                <div className="chip-row" aria-label="Fill in a known service">
                  {PRESETS.map(([name, url]) => (
                    <button
                      key={name}
                      type="button"
                      className={`chip small ${form.base_url === url ? "on" : ""}`}
                      onClick={() => setForm((f) => ({ ...f, base_url: url }))}
                    >
                      {name}
                    </button>
                  ))}
                </div>
                <label className="field">
                  <span>Address (base URL)</span>
                  <input
                    value={form.base_url}
                    onChange={(e) => setForm((f) => ({ ...f, base_url: e.target.value }))}
                    placeholder="https://…/v1"
                    spellCheck={false}
                  />
                </label>
              </>
            )}

            <label className="field">
              <span>
                <KeyRound size={14} /> API key {form.provider === "openai" && "(leave empty for local models)"}
              </span>
              <input
                type="password"
                autoComplete="off"
                spellCheck={false}
                value={keyInput}
                onChange={(e) => {
                  setKeyInput(e.target.value);
                  setRemoveKey(false);
                }}
                placeholder={
                  keyCarries && !removeKey
                    ? `Saved key ${saved?.key_hint} — leave empty to keep it`
                    : needsKey
                      ? "sk-ant-…"
                      : "Paste the key from your provider"
                }
              />
              {keyCarries && !keyInput && (
                <button type="button" className="text-link small-link" onClick={() => setRemoveKey(!removeKey)}>
                  {removeKey ? "Keep the saved key" : "Remove the saved key"}
                </button>
              )}
              <small>
                Stored only on the server running Crowdpod (in <code>data/settings.json</code>), never sent back to
                this page, and only used for the service it was entered for.
              </small>
            </label>

            <div className="field-row">
              <label className="field">
                <span>Model</span>
                {form.provider === "anthropic" && !models.length ? (
                  <select value={form.model} onChange={(e) => setForm((f) => ({ ...f, model: e.target.value }))}>
                    {CLAUDE_MODELS.map(([id, label]) => (
                      <option key={id} value={id}>
                        {label}
                      </option>
                    ))}
                  </select>
                ) : (
                  <>
                    <input
                      list="model-list"
                      value={form.model}
                      onChange={(e) => setForm((f) => ({ ...f, model: e.target.value }))}
                      placeholder="model name"
                      spellCheck={false}
                    />
                    <datalist id="model-list">
                      {models.map((m) => (
                        <option key={m} value={m} />
                      ))}
                    </datalist>
                  </>
                )}
              </label>
              {form.provider === "anthropic" ? (
                <label className="field">
                  <span>Effort per decision</span>
                  <select
                    value={form.effort}
                    onChange={(e) => setForm((f) => ({ ...f, effort: e.target.value as BrainForm["effort"] }))}
                  >
                    <option value="low">Low — fastest, cheapest</option>
                    <option value="medium">Medium (recommended)</option>
                    <option value="high">High — most careful</option>
                  </select>
                </label>
              ) : (
                <div className="field field-action">
                  <span>&nbsp;</span>
                  <button
                    type="button"
                    className="chip"
                    onClick={() => run("models")}
                    disabled={!!busy || (form.provider === "openai" && !form.base_url)}
                  >
                    {busy === "models" && <Loader2 className="spin" size={14} />} Load models from this address
                  </button>
                </div>
              )}
            </div>

            <details className="advanced">
              <summary>Advanced</summary>
              <div className="field-row">
                <label className="field">
                  <span>Calls at once</span>
                  <input
                    type="number"
                    min={1}
                    max={32}
                    value={form.concurrency}
                    onChange={(e) => setForm((f) => ({ ...f, concurrency: Number(e.target.value) }))}
                  />
                </label>
                <label className="field">
                  <span>Personas per call</span>
                  <input
                    type="number"
                    min={1}
                    max={50}
                    value={form.batch_size}
                    onChange={(e) => setForm((f) => ({ ...f, batch_size: Number(e.target.value) }))}
                  />
                </label>
              </div>
              <small>Lower both for local models or free tiers with strict rate limits.</small>
            </details>
          </div>
        )}
      </section>

      <section className="app-card">
        <span className="mini-label">
          <MonitorPlay size={13} /> BROWSER AGENTS
        </span>
        <h2>
          Watch them <em>use the site.</em>
        </h2>
        <label className="toggle">
          <input
            type="checkbox"
            checked={browser.show_windows}
            onChange={(e) => setBrowser((b) => ({ ...b, show_windows: e.target.checked }))}
          />
          <span>Open visible Chromium windows on this computer while personas browse</span>
        </label>
        <div className="field-row">
          <label className="field">
            <span>Slow motion: {browser.slow_mo_ms} ms per action</span>
            <input
              type="range"
              min={0}
              max={2000}
              step={100}
              value={browser.slow_mo_ms}
              onChange={(e) => setBrowser((b) => ({ ...b, slow_mo_ms: Number(e.target.value) }))}
            />
          </label>
          <label className="field">
            <span>Browsers at once</span>
            <input
              type="number"
              min={1}
              max={8}
              value={browser.parallel}
              onChange={(e) => setBrowser((b) => ({ ...b, parallel: Number(e.target.value) }))}
            />
          </label>
        </div>
      </section>

      <div className="settings-actions">
        {form.provider !== "mock" && (
          <button className="chip" onClick={() => run("test")} disabled={!!busy}>
            {busy === "test" ? <Loader2 className="spin" size={14} /> : <PlugZap size={14} />} Test connection
          </button>
        )}
        <button className="button" onClick={() => run("save")} disabled={!!busy}>
          {busy === "save" && <Loader2 className="spin" size={17} />} Save settings
        </button>
        {result && (
          <p className={`test-result ${result.ok ? "ok" : "bad"}`} role="status">
            {result.ok ? <Check size={15} /> : <X size={15} />} {result.text}
          </p>
        )}
      </div>
    </>
  );
}

function TokensSection({ onCreated }: { onCreated: (token: string) => void }) {
  const [tokens, setTokens] = useState<AccessToken[]>([]);
  const [name, setName] = useState("my agent");
  const [fresh, setFresh] = useState("");
  const [error, setError] = useState("");
  const load = () => api.tokens().then(setTokens).catch((e) => setError(e instanceof Error ? e.message : String(e)));
  useEffect(() => {
    load();
  }, []);
  const create = async () => {
    setError("");
    try {
      const t = await api.createToken(name);
      setFresh(t.token);
      onCreated(t.token);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };
  const revoke = async (id: string) => {
    await api.revokeToken(id).catch(() => {});
    load();
  };
  const when = (s: number | null) => (s ? new Date(s * 1000).toLocaleString() : "never");
  return (
    <section className="app-card">
      <span className="mini-label">
        <KeyRound size={13} /> ACCESS TOKENS
      </span>
      <h2>
        Keys for <em>your agents.</em>
      </h2>
      <p className="app-lede">
        A token lets an agent on your computer use Crowdpod as you: run simulations and read your results. It can&apos;t
        change your account or create more tokens. Revoke it here if it leaks.
      </p>
      <div className="field-row">
        <label className="field">
          <span>Name</span>
          <input value={name} maxLength={60} onChange={(e) => setName(e.target.value)} />
        </label>
        <div className="field field-action">
          <span>&nbsp;</span>
          <button className="chip" onClick={create}>
            <KeyRound size={14} /> Create token
          </button>
        </div>
      </div>
      {fresh && (
        <>
          <div className="code-box">
            <pre>{fresh}</pre>
            <CopyButton text={fresh} />
          </div>
          <p className="mcp-hint">Copy it now: it won&apos;t be shown again. The setup below already includes it.</p>
        </>
      )}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {tokens.length > 0 && (
        <ul className="token-list">
          {tokens.map((t) => (
            <li key={t.id}>
              <span>
                <b>{t.name}</b> <small>created {when(t.created_at)} · last used {when(t.last_used)}</small>
              </span>
              <button className="text-link small-link" onClick={() => revoke(t.id)}>
                <Trash2 size={13} /> Revoke
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      className="copy"
      aria-label="Copy"
      onClick={() => {
        navigator.clipboard.writeText(text).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        });
      }}
    >
      {copied ? <Check size={15} /> : <Copy size={15} />}
    </button>
  );
}

const CLIENTS = [
  ["claude_code", "Claude Code", "Run this once in a terminal:"],
  ["codex", "Codex", "Add this to ~/.codex/config.toml:"],
  ["claude_desktop", "Claude Desktop", "Add this to claude_desktop_config.json (Settings → Developer → Edit config):"],
  ["opencode", "OpenCode", "Add this to opencode.json in your project (or merge it into ~/.config/opencode/opencode.json):"],
] as const;

function McpSection({ token }: { token: string }) {
  const [setup, setSetup] = useState<McpSetup | null>(null);
  const [tab, setTab] = useState<(typeof CLIENTS)[number][0]>("claude_code");
  useEffect(() => {
    api.mcpSetup().then(setSetup).catch(() => setSetup(null));
  }, []);
  const current = CLIENTS.find(([id]) => id === tab)!;
  // the token stays in this page: the server only ever sends the PASTE_YOUR_TOKEN placeholder
  const text = setup ? (token ? setup[tab].replaceAll("PASTE_YOUR_TOKEN", token) : setup[tab]) : "";
  return (
    <section className="app-card mcp-section">
      <span className="mini-label">
        <Plug size={13} /> MCP
      </span>
      <h2>
        Use Crowdpod from <em>your own AI tools.</em>
      </h2>
      <p className="app-lede">
        Connect Crowdpod to Claude Code, Codex, Claude Desktop or OpenCode. Your tool keeps its own sign-in and
        subscription; Crowdpod never sees it. Your agent can then run crowd simulations, read the BRD and PRD, interview personas,
        and even play a persona itself in a real browser, step by step.
      </p>
      <div className="chip-row" role="tablist" aria-label="AI tool">
        {CLIENTS.map(([id, label]) => (
          <button key={id} role="tab" aria-selected={tab === id} className={`chip ${tab === id ? "on" : ""}`} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </div>
      <p className="mcp-hint">{current[2]}</p>
      <div className="code-box">
        <pre>{setup ? text : "Start the Crowdpod server to see the setup."}</pre>
        {setup && <CopyButton text={text} />}
      </div>
      {setup?.needs_token && !token && (
        <p className="mcp-hint">Create an access token above and it will be filled in here (or replace PASTE_YOUR_TOKEN yourself).</p>
      )}
      {setup && (
        <>
          <p className="mcp-hint">
            Needs{" "}
            <a href="https://docs.astral.sh/uv/" target="_blank" rel="noreferrer">
              uv
            </a>
            . For live browser visits, install Chromium once:
          </p>
          <div className="code-box">
            <pre>{setup.browsers}</pre>
            <CopyButton text={setup.browsers} />
          </div>
        </>
      )}
      <p className="mcp-hint">
        {setup?.needs_token ? (
          "Simulations run on this site."
        ) : (
          <>
            Keep <code>uv run crowdpod serve</code> running for simulations.
          </>
        )}{" "}
        Then ask your agent, for example:{" "}
        <em>“Use Crowdpod to test my idea for a hostel tiffin service with 300 people, then visit my site as a student
        looking for the price.”</em>
      </p>
      <ul className="tool-list">
        <li><b>start_simulation</b>, <b>get_results</b>, <b>get_documents</b>: run a crowd and read the verdict, BRD and PRD</li>
        <li><b>interview_persona</b>: ask one simulated person a follow-up question</li>
        <li><b>visit_as_persona</b>, <b>browser_step</b>, <b>end_visit</b>: your agent plays a persona in Chromium and sees each page</li>
      </ul>
    </section>
  );
}
