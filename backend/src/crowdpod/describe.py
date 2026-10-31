"""People the user describes in a sentence, turned into full personas.

"A final-year engineering student in Pune, broke, only uses free apps" becomes a persona with an age
range, city, budgets, patience, tech comfort, price sensitivity, moods, devices, objections and
must-haves. A model brain writes it from `vault/templates/persona-from-brief.md`, keeping what the
user said as fixed facts and filling the rest realistically. The offline brain builds it from the
closest built-in archetype, adjusted by what the description says (age, city, money, temperament).
"""

from __future__ import annotations

import re

from .models import GeneratedPersona, IdeaBrief
from .vault import Vault

CITIES = (
    "mumbai", "delhi", "new delhi", "bengaluru", "bangalore", "hyderabad", "chennai", "kolkata", "pune",
    "ahmedabad", "jaipur", "lucknow", "kanpur", "nagpur", "indore", "bhopal", "patna", "surat", "kochi",
    "chandigarh", "coimbatore", "noida", "gurugram", "gurgaon", "goa", "mysuru", "vizag", "bhubaneswar",
    "guwahati", "dehradun", "ranchi", "raipur", "nashik", "vadodara", "ludhiana", "amritsar", "varanasi",
)
DEVICES = {"iphone": "iphone", "ipad": "ipad", "laptop": "laptop", "macbook": "laptop", "pc": "laptop",
           "budget phone": "budget-android", "cheap phone": "budget-android", "old phone": "budget-android",
           "android": "mid-android", "tablet": "shared-tablet"}
MOODS = ("stressed", "tired", "curious", "excited", "anxious", "bored", "rushed", "skeptical", "hopeful",
         "frustrated", "relaxed", "distracted")

# what a description says about a person, as (pattern, field, range). Later matches win, so each
# field lists the general phrase first and the negated or stronger one after it ("not tech-savvy").
TRAITS: list[tuple[str, str, tuple[float, float]]] = [
    (r"\b(rich|wealthy|affluent|premium|luxury|high income)\b|money is no|doesn'?t care about (the )?price", "price_sensitivity", (0.1, 0.3)),
    (r"\b(broke|cheap|frugal)\b|tight budget|low income|saving money|every rupee|can'?t afford|free apps?|careful with money", "price_sensitivity", (0.8, 0.95)),
    (r"\bpatient\b|\bcareful\b|thorough|researches|compares everything", "patience_seconds", (60, 150)),
    (r"impatient|\bbusy\b|no time|in a hurry|short attention|rushed", "patience_seconds", (10, 25)),
    (r"techie|tech-?savvy|developer|programmer|software|early adopter|gadget|geek", "tech_comfort", (0.75, 0.95)),
    (r"not (very )?tech|non-?tech|elderly|grand(ma|pa|mother|father)|retired|first smartphone|struggles with (apps|phones)", "tech_comfort", (0.1, 0.35)),
    (r"enthusiast|\bloves\b|excited about|early adopter|optimistic|fan of", "sentiment_bias", (0.2, 0.6)),
    (r"skeptic|sceptic|distrust|\bhates\b|cynical|burned before|doesn'?t trust", "sentiment_bias", (-0.6, -0.15)),
]
# who someone is, to the built-in persona that lives most like them
ROLES: list[tuple[str, str]] = [
    (r"student|college|undergrad|hostel", "student"),
    (r"mother|\bmom\b|\bmum\b|housewife|homemaker|parent of", "mother"),
    (r"father|\bdad\b|stay-at-home", "househusband"),
    (r"driver|auto|rickshaw|\bcab\b|delivery|gig worker|daily wage|shopkeeper|vendor", "auto-driver"),
    (r"\bceo\b|founder|business owner|entrepreneur|director|executive", "ceo"),
    (r"athlete|runner|cricketer|gym|fitness|sports", "athlete"),
    (r"dancer|artist|musician|creator|designer|freelanc", "dancer"),
    (r"recruiter|\bhr\b|hiring", "recruiter"),
    (r"placement|teacher|professor|lecturer|principal|tutor", "placement-officer"),
    (r"manager|engineer|developer|analyst|consultant|office|corporate|employee|banker|accountant|\bjob\b", "corporate-worker"),
]


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 2}


def _closest(vault: Vault, text: str) -> str:
    """The built-in archetype for this kind of person: by role first, else by shared words."""
    for pattern, aid in ROLES:
        if aid in vault.archetypes and re.search(pattern, text, re.IGNORECASE):
            return aid
    words = _words(text)

    def score(aid: str) -> int:
        a = vault.archetypes[aid]
        vocab = _words(" ".join([a.id.replace("-", " "), a.label, a.profession, *a.interests, *a.pains]))
        return len(words & vocab)

    builtin = [aid for aid, a in vault.archetypes.items() if not a.generated_for]
    return max(builtin, key=score)


def _age(text: str) -> tuple[float, float] | None:
    t = text.lower()
    if m := re.search(r"\b(\d{2})s\b", t):  # "in her 40s"
        n = int(m.group(1))
        return (n, n + 9)
    if m := re.search(r"\b(\d{2})\s*(?:-|\s)?(?:yo|y/o|years?|yrs?)\b|\baged?\s*(\d{2})\b", t):
        n = int(m.group(1) or m.group(2))
        return (max(14, n - 2), n + 2)
    for words, rng in ((r"teen", (15, 19)), (r"college|student|undergrad", (18, 24)), (r"retired|elderly|senior citizen", (60, 75))):
        if re.search(words, t):
            return rng
    return None


def _money(text: str) -> tuple[str, tuple[float, float]] | None:
    """A rupee amount, and whether it's a monthly budget or a one-off one."""
    m = re.search(r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d+)?)\s*(k|lakh|lac)?|([\d,]+(?:\.\d+)?)\s*(k|lakh|lac)?\s*(?:rupees|rs\b|inr)",
                  text, re.IGNORECASE)
    if not m:
        return None
    num = float((m.group(1) or m.group(3)).replace(",", ""))
    unit = (m.group(2) or m.group(4) or "").lower()
    num *= 1000 if unit == "k" else 100_000 if unit in ("lakh", "lac") else 1
    after = text[m.end():m.end() + 25].lower()
    field = "budget_month" if re.search(r"month|/mo|pm\b|monthly", after + text.lower()) else "purchase_budget"
    return field, (round(num * 0.7), round(num * 1.2))


def _label(text: str) -> str:
    first = re.split(r"[,.;:—–(]| who | that | with | in | from ", text.strip(), maxsplit=1)[0]
    words = first.split()[:6]
    label = " ".join(words).strip()
    label = re.sub(r"^(a|an|the|my|some)\s+", "", label, flags=re.IGNORECASE)
    return (label[:1].upper() + label[1:])[:60] or "Described person"


def persona_from_description(text: str, brief: IdeaBrief, vault: Vault, index: int) -> GeneratedPersona:
    """Offline: the closest built-in archetype, reshaped by what the description says."""
    base = vault.archetypes[_closest(vault, text)]
    t = text.lower()
    fields: dict[str, tuple[float, float]] = {
        "age": base.age, "budget_month": base.budget_month, "purchase_budget": base.purchase_budget,
        "patience_seconds": base.patience_seconds, "tech_comfort": base.tech_comfort,
        "price_sensitivity": base.price_sensitivity, "sentiment_bias": base.sentiment_bias,
    }
    for pattern, field, rng in TRAITS:
        if re.search(pattern, t):
            fields[field] = rng
    if age := _age(text):
        fields["age"] = age
    if money := _money(text):
        fields[money[0]] = money[1]
    objections = list(base.objections)
    if fields["price_sensitivity"][0] >= 0.7:
        objections.insert(0, "It costs more than I can spend on something like this")
    if fields["patience_seconds"][1] <= 30:
        objections.insert(0, "If I can't see what it does in a few seconds, I'm gone")
    if fields["tech_comfort"][1] <= 0.4:
        objections.insert(0, "Too complicated; I'd need someone to set it up for me")

    city = next((c.title() for c in CITIES if re.search(rf"\b{c}\b", t)), base.city)
    devices = list(dict.fromkeys(d for k, d in DEVICES.items() if k in t)) or list(base.devices)
    moods = [m for m in MOODS if m in t] or list(base.moods)
    label = _label(text)
    return GeneratedPersona(
        id=f"described-{index + 1}-{re.sub(r'[^a-z0-9]+', '-', label.lower()).strip('-')[:30]}",
        label=label,
        share=0.15,
        profession=base.profession,
        city=city,
        names=list(base.names) or ["Asha", "Ravi", "Meera"],
        age=fields["age"], budget_month=fields["budget_month"], purchase_budget=fields["purchase_budget"],
        patience_seconds=fields["patience_seconds"], tech_comfort=fields["tech_comfort"],
        price_sensitivity=fields["price_sensitivity"], sentiment_bias=fields["sentiment_bias"],
        moods=moods, devices=devices,
        interests=list(base.interests), pains=list(base.pains), objections=objections[:8],
        must_haves=list(base.must_haves), goals_on_site=list(base.goals_on_site),
        who_they_are=text.strip(),
        how_they_decide=f"Decides like a {base.label.lower()}: {', '.join(base.must_haves[:2]) or 'value for money'} matter most.",
        how_they_talk=f"Talks like a {base.label.lower()} from {city}.",
        sample_quotes=(base.voice.maybe + base.voice.reject)[:4] or ["Hmm, let me think."],
        evidence=[f"Described by the user: {text.strip()}", f"Filled in from the built-in '{base.label}' persona (offline brain)"],
    )
