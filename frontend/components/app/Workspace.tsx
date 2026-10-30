"use client";
import { useEffect, useState, type FormEvent } from "react";
import { ArrowUpRight, Loader2, MousePointerClick, UsersRound } from "lucide-react";
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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.archetypes().then(setArchetypes).catch(() => {});
    api.runs().then(setRuns).catch(() => {});
  }, []);

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
        mix: excluded.size ? Object.fromEntries(included.map((a) => [a.id, a.weight])) : null,
        hands: url ? { url, personas: handsCount, archetypes: handsFirst, goal: goal.trim() || null } : null,
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
          <div className="chip-row" aria-label="Segments in the crowd">
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
              <small>Pick segments to send first, or leave empty and Crowdpod picks the ones that matter.</small>
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
