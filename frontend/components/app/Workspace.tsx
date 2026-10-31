"use client";
import { useEffect, useState, type FormEvent } from "react";
import { ArrowUpRight, Loader2, MousePointerClick, Plus, Search, UserRoundPen, UsersRound, X } from "lucide-react";
import { Eyebrow } from "../landing/UI";
import { api, type Archetype, type PricePeriod, type RunListItem } from "@/lib/api";

const periods: [PricePeriod, string][] = [
  ["month", "per month"],
  ["year", "per year"],
  ["one_time", "one-time"],
  ["free", "free"],
];

export default function Workspace() {
  const [archetypes, setArchetypes] = useState<Archetype[]>([]);
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [name, setName] = useState("");
  const [pitch, setPitch] = useState("");
  const [category, setCategory] = useState("");
  const [target, setTarget] = useState("");
  const [price, setPrice] = useState("");
  const [period, setPeriod] = useState<PricePeriod>("month");
  const [size, setSize] = useState(300);
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [url, setUrl] = useState("");
  const [handsCount, setHandsCount] = useState(5);
  const [handsFirst, setHandsFirst] = useState<string[]>([]);
  const [goal, setGoal] = useState("");
  const [audience, setAudience] = useState<"generated" | "builtin" | "both">("generated");
  const [audienceSize, setAudienceSize] = useState(6);
  const [notes, setNotes] = useState("");
  const [people, setPeople] = useState<string[]>([""]);
  const [brain, setBrain] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.archetypes().then(setArchetypes).catch(() => {});
    api.runs().then(setRuns).catch(() => {});
    api.health().then((h) => setBrain(h.provider ?? null)).catch(() => {});
  }, []);
  const offline = brain === "mock";
  const usesBuiltin = audience !== "generated" || offline;

  const included = archetypes.filter((a) => !excluded.has(a.id));
  const toggle = (id: string) =>
    setExcluded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else if (archetypes.length - next.size > 1) next.add(id);
      return next;
    });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!name.trim() || pitch.trim().length < 10) {
      setError("Give the idea a name and describe it in at least a sentence.");
      return;
    }
    const amount = period === "free" ? 0 : Number(price || 0);
    if (Number.isNaN(amount) || amount < 0) {
      setError("Price must be a number.");
      return;
    }
    if (url && !/^https?:\/\//.test(url)) {
      setError("The website address must start with http:// or https://");
      return;
    }
    setBusy(true);
    try {
      const { run_id } = await api.createRun({
        brief: {
          name: name.trim(),
          pitch: pitch.trim(),
          category: category.trim(),
          target_hint: target.trim(),
          price: amount,
          currency: "INR",
          price_period: period,
          url: url || null,
        },
        crowd_size: size,
        mix: usesBuiltin && excluded.size ? Object.fromEntries(included.map((a) => [a.id, a.weight])) : null,
        audience,
        audience_size: audienceSize,
        context_notes: notes.trim(),
        described: people.map((p) => p.trim()).filter(Boolean),
        hands: url
          ? { url, personas: handsCount, archetypes: usesBuiltin ? handsFirst : [], goal: goal.trim() || null }
          : null,
      });
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- static export writes nested-route payloads where the client router can't find them; use a full page load
      window.location.assign(`/app/run/?id=${run_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  };

  return (
    <div className="workspace">
      <form className="app-card idea-form" onSubmit={submit}>
        <Eyebrow>NEW SIMULATION</Eyebrow>
        <h1>
          What are you <em>building?</em>
        </h1>
        <p className="app-lede">
          Describe the idea the way you’d explain it to a stranger. The crowd only knows what you write here.
        </p>

        <label className="field">
          <span>Name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} placeholder="What it’s called" />
        </label>
        <label className="field">
          <span>The idea</span>
          <textarea
            value={pitch}
            onChange={(e) => setPitch(e.target.value)}
            maxLength={4000}
            rows={6}
            placeholder="What it does, who it’s for, and why they’d care."
          />
          <small>{pitch.length}/4000</small>
        </label>
        <div className="field-row">
          <label className="field">
            <span>Category</span>
            <input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="e.g. edtech, food delivery" />
          </label>
          <label className="field">
            <span>Who you think it’s for</span>
            <input value={target} onChange={(e) => setTarget(e.target.value)} placeholder="Your current guess" />
          </label>
        </div>
        <div className="field-row">
          <label className="field">
            <span>Price (₹)</span>
            <input
              inputMode="decimal"
              value={period === "free" ? "0" : price}
              disabled={period === "free"}
              onChange={(e) => setPrice(e.target.value)}
              placeholder="0"
            />
          </label>
          <label className="field">
            <span>Billed</span>
            <select value={period} onChange={(e) => setPeriod(e.target.value as PricePeriod)}>
              {periods.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </label>
        </div>

        <fieldset className="field">
          <legend>
            <Search size={15} /> Who is in the crowd
          </legend>
          <div className="chip-row" role="radiogroup" aria-label="Audience">
            {(
              [
                ["generated", "Research & create personas for this idea"],
                ["both", "Created + built-in personas"],
                ["builtin", "Built-in personas only"],
              ] as const
            ).map(([value, label]) => (
              <button
                type="button"
                key={value}
                role="radio"
                aria-checked={audience === value}
                className={`chip ${audience === value ? "on" : ""}`}
                onClick={() => setAudience(value)}
              >
                {label}
              </button>
            ))}
          </div>
          {audience !== "builtin" && (
            <>
              <small>
                {offline
                  ? "The offline brain can't research, so this run will use the built-in personas. Choose Claude or another model in Settings to research the market."
                  : "The brain researches this idea's market (Claude searches the web live), then designs personas with realistic budgets. They're saved with this simulation."}
              </small>
              {!offline && (
                <>
                  <label className="inline-field">
                    <span>Personas to create</span>
                    <input
                      type="number"
                      min={3}
                      max={10}
                      value={audienceSize}
                      onChange={(e) => setAudienceSize(Math.max(3, Math.min(10, Number(e.target.value))))}
                    />
                  </label>
                  <textarea
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    maxLength={6000}
                    rows={3}
                    placeholder="Optional: what you already know about this market (competitors, prices, who buys)."
                    aria-label="What you already know about the market"
                  />
                </>
              )}
            </>
          )}
        </fieldset>

        <fieldset className="field">
          <legend>
            <UserRoundPen size={15} /> Specific people you want in the crowd (optional)
          </legend>
          <small>
            Describe someone in a sentence. Crowdpod fills in the rest the way such a person really lives: age, city,
            budget, patience, tech comfort, moods, devices and what makes them say no. Each one becomes their own
            group in the crowd.
          </small>
          {people.map((p, i) => (
            <div className="person-row" key={i}>
              <input
                value={p}
                maxLength={400}
                onChange={(e) => setPeople((all) => all.map((x, j) => (j === i ? e.target.value : x)))}
                placeholder={
                  [
                    "e.g. A final-year engineering student in Pune, broke, only uses free apps",
                    "e.g. A retired teacher in her 60s from Jaipur, not tech-savvy, careful with money",
                    "e.g. A busy product manager in Bengaluru with an iPhone, impatient with long forms",
                  ][i % 3]
                }
                aria-label={`Person ${i + 1}`}
              />
              {people.length > 1 && (
                <button
                  type="button"
                  className="chip small"
                  aria-label={`Remove person ${i + 1}`}
                  onClick={() => setPeople((all) => all.filter((_, j) => j !== i))}
                >
                  <X size={13} />
                </button>
              )}
            </div>
          ))}
          {people.length < 5 && (
            <button type="button" className="chip small" onClick={() => setPeople((all) => [...all, ""])}>
              <Plus size={13} /> Add a person
            </button>
          )}
        </fieldset>

        <fieldset className="field">
          <legend>
            <UsersRound size={15} /> The crowd · {size.toLocaleString("en-IN")} people
          </legend>
          <input
            type="range"
            min={50}
            max={2000}
            step={50}
            value={size}
            onChange={(e) => setSize(Number(e.target.value))}
            aria-label="Crowd size"
          />
          {usesBuiltin && (
          <div className="chip-row" aria-label="Built-in segments in the crowd">
            {archetypes.map((a) => (
              <button
                type="button"
                key={a.id}
                className={`chip ${excluded.has(a.id) ? "" : "on"}`}
                aria-pressed={!excluded.has(a.id)}
                onClick={() => toggle(a.id)}
                title={a.profession}
              >
                {a.label}
              </button>
            ))}
          </div>
          )}
        </fieldset>

        <fieldset className="field">
          <legend>
            <MousePointerClick size={15} /> Hands · optional
          </legend>
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://your-landing-page.com"
            aria-label="Website for the hands to use"
          />
          {url && (
            <>
              <input
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                maxLength={300}
                placeholder="What should they try to do? e.g. find out how to apply for a drive"
                aria-label="What the visitors should try to do"
              />
              <small>Leave empty and each persona pursues their own usual goal.</small>
              <label className="inline-field">
                <span>Personas who visit</span>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={handsCount}
                  onChange={(e) => setHandsCount(Math.max(1, Math.min(20, Number(e.target.value))))}
                />
              </label>
              {usesBuiltin && (
              <div className="chip-row" aria-label="Send these segments first">
                {included.map((a) => (
                  <button
                    type="button"
                    key={a.id}
                    className={`chip small ${handsFirst.includes(a.id) ? "on" : ""}`}
                    aria-pressed={handsFirst.includes(a.id)}
                    onClick={() =>
                      setHandsFirst((h) => (h.includes(a.id) ? h.filter((x) => x !== a.id) : [...h, a.id]))
                    }
                  >
                    {a.label}
                  </button>
                ))}
              </div>
              )}
              <small>
                {usesBuiltin
                  ? "Pick segments to send first, or leave empty and Crowdpod picks the ones that matter."
                  : "Crowdpod sends the created personas that matter most: the strongest segment, the weakest, then the rest."}
              </small>
            </>
          )}
        </fieldset>

        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <button className="button" type="submit" disabled={busy}>
          {busy ? <Loader2 className="spin" size={17} /> : null}
          {busy ? "Gathering the crowd…" : "Ask the crowd"}
          {!busy && <ArrowUpRight size={17} />}
        </button>
      </form>

      <aside className="app-card recent-runs">
        <span className="mini-label">RECENT SIMULATIONS</span>
        {runs.length === 0 ? (
          <p className="app-empty">Nothing yet. Your first idea goes here.</p>
        ) : (
          <ul>
            {runs.map((r) => (
              <li key={r.id}>
                <a href={`/app/run/?id=${r.id}`}>
                  <strong>{r.name}</strong>
                  <span className={`status-pill ${r.status}`}>{r.status}</span>
                  <small>{new Date(r.created_at * 1000).toLocaleString()}</small>
                </a>
              </li>
            ))}
          </ul>
        )}
      </aside>
    </div>
  );
}
