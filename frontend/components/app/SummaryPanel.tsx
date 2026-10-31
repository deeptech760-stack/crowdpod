"use client";
import { money, pct, priced, type CrowdSummary } from "@/lib/api";

export default function SummaryPanel({ summary: s }: { summary: CrowdSummary }) {
  const maxCount = Math.max(...s.segments.map((x) => x.count), 1);
  return (
    <section className="app-card summary-section">
      <span className="mini-label">THE SIGNAL</span>
      <h2 className="headline">{s.headline}</h2>
      <div className="stat-row">
        <Stat label="Would adopt" value={pct(s.adoption_rate)} />
        <Stat label="At least interested" value={pct(s.interest_rate)} />
        <Stat label="The interested would pay (median)" value={priced(s.median_wtp_interested ?? s.median_wtp, s.price_unit)} />
        <Stat label="Your price fits their budget" value={pct(s.price_fit_rate)} />
      </div>

      <div className="table-wrap">
        <table className="segment-table">
          <thead>
            <tr>
              <th scope="col">Segment</th>
              <th scope="col">Verdicts</th>
              <th scope="col">Adopt</th>
              <th scope="col">{s.price_unit === "one_time" ? "Median ₹ (one-time)" : "Median ₹/mo"}</th>
              <th scope="col">Budget fits</th>
            </tr>
          </thead>
          <tbody>
            {s.segments.map((seg) => (
              <tr key={seg.archetype_id} className={seg.archetype_id === s.best_segment ? "best" : ""}>
                <th scope="row">
                  {seg.label}
                  {seg.archetype_id === s.best_segment && <span className="tag">your market</span>}
                  <small>{seg.count} people</small>
                </th>
                <td>
                  <span className="verdict-bar" style={{ width: `${(seg.count / maxCount) * 100}%` }}>
                    <i className="adopt" style={{ flex: seg.adopt }} />
                    <i className="maybe" style={{ flex: seg.maybe }} />
                    <i className="reject" style={{ flex: seg.reject }} />
                  </span>
                </td>
                <td>{pct(seg.adoption_rate)}</td>
                <td>{money(seg.median_wtp)}</td>
                <td>{pct(seg.price_fit_rate)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="two-lists">
        <div>
          <h3>Why they say no</h3>
          <Ranked items={s.top_objections} total={s.size} />
        </div>
        <div>
          <h3>What would make them pay</h3>
          <Ranked items={s.top_must_haves} total={s.size} />
        </div>
      </div>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat">
      <strong>{value}</strong>
      <small>{label}</small>
    </div>
  );
}

function Ranked({ items, total }: { items: [string, number][]; total: number }) {
  if (!items.length) return <p className="app-empty">Nothing stood out.</p>;
  const max = items[0][1];
  return (
    <ol className="ranked">
      {items.map(([text, n]) => (
        <li key={text}>
          <span>{text}</span>
          <i style={{ width: `${(n / max) * 100}%` }} />
          <small>
            {n} · {pct(n / total)}
          </small>
        </li>
      ))}
    </ol>
  );
}
