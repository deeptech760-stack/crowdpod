"""Stage 4: plain statistics over the reactions. No model involved."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from statistics import mean, median

from .models import Archetype, CrowdSummary, IdeaBrief, Persona, Reaction, SegmentStats

MIN_SEGMENT = 5  # a segment smaller than this can't be named the best market


def plural(label: str) -> str:
    """"Corporate worker" -> "corporate workers", "CEO" -> "CEOs"."""
    return (label if label.isupper() else label.lower()) + "s"


def _norm(text: str) -> str:
    return re.sub(r"[^\w\s₹]", "", text.lower()).strip()


def top_phrases(items: list[str], n: int = 5) -> list[tuple[str, int]]:
    """Count phrases, merging case and punctuation variants; report the most common spelling."""
    counts: Counter[str] = Counter()
    spelling: dict[str, Counter[str]] = defaultdict(Counter)
    for raw in items:
        raw = raw.strip()
        if not raw:
            continue
        key = _norm(raw)
        counts[key] += 1
        spelling[key][raw] += 1
    return [(spelling[k].most_common(1)[0][0], c) for k, c in counts.most_common(n)]


def summarise(
    brief: IdeaBrief, crowd: list[Persona], reactions: list[Reaction], archetypes: dict[str, Archetype]
) -> CrowdSummary:
    if len(crowd) != len(reactions):
        raise ValueError("every persona needs exactly one reaction")
    price = brief.monthly_price
    total = len(crowd)
    groups: dict[str, list[tuple[Persona, Reaction]]] = defaultdict(list)
    for p, r in zip(crowd, reactions):
        groups[p.archetype_id].append((p, r))

    def paying(r: Reaction) -> bool:
        return r.verdict == "adopt" and r.willingness_to_pay >= price

    segments: list[SegmentStats] = []
    for arch_id, rows in groups.items():
        rs = [r for _, r in rows]
        n = len(rs)
        verdicts = Counter(r.verdict for r in rs)
        segments.append(SegmentStats(
            archetype_id=arch_id,
            label=archetypes[arch_id].label if arch_id in archetypes else arch_id,
            count=n,
            adopt=verdicts["adopt"], maybe=verdicts["maybe"], reject=verdicts["reject"],
            adoption_rate=round(verdicts["adopt"] / n, 3),
            interest_rate=round((verdicts["adopt"] + verdicts["maybe"]) / n, 3),
            avg_sentiment=round(mean(r.sentiment for r in rs), 3),
            median_wtp=float(median(r.willingness_to_pay for r in rs)),
            price_fit_rate=round(sum(p.budget_month >= price for p, _ in rows) / n, 3),
            # share of the whole crowd that this segment turns into paying customers
            score=round(sum(paying(r) for r in rs) / total, 4),
            top_objections=top_phrases([r.top_objection for r in rs if r.verdict != "adopt"], 3),
            top_must_haves=top_phrases([r.must_have for r in rs], 3),
        ))
    segments.sort(key=lambda s: (s.score, s.adoption_rate), reverse=True)

    eligible = [s for s in segments if s.count >= MIN_SEGMENT] or segments
    best = eligible[0] if eligible and eligible[0].score > 0 else None
    worst = min(eligible, key=lambda s: (s.interest_rate, s.avg_sentiment)) if eligible else None

    adoption = sum(r.verdict == "adopt" for r in reactions) / total
    interest = sum(r.verdict != "reject" for r in reactions) / total
    summary = CrowdSummary(
        size=total,
        monthly_price=price,
        adoption_rate=round(adoption, 3),
        interest_rate=round(interest, 3),
        median_wtp=float(median(r.willingness_to_pay for r in reactions)),
        median_wtp_interested=float(median([r.willingness_to_pay for r in reactions if r.verdict != "reject"] or [0])),
        price_fit_rate=round(sum(p.budget_month >= price for p in crowd) / total, 3),
        best_segment=best.archetype_id if best else None,
        worst_segment=worst.archetype_id if worst else None,
        segments=segments,
        top_objections=top_phrases([r.top_objection for r in reactions if r.verdict != "adopt"], 6),
        top_must_haves=top_phrases([r.must_have for r in reactions], 6),
        headline="",
    )
    summary.headline = headline(brief, summary)
    return summary


def headline(brief: IdeaBrief, s: CrowdSummary) -> str:
    if not s.best_segment:
        return f"Nobody in a crowd of {s.size} would pay ₹{s.monthly_price:g}/month for {brief.name}."
    best = next(x for x in s.segments if x.archetype_id == s.best_segment)
    line = (
        f"Your market is {plural(best.label)}: {best.adoption_rate:.0%} would adopt, "
        f"median willingness to pay ₹{best.median_wtp:g}/month."
    )
    hint = brief.target_hint.lower()
    if hint and best.label.lower() not in hint and best.archetype_id.replace("-", " ") not in hint:
        line = f"Your market isn't {brief.target_hint}. " + line
    return line
