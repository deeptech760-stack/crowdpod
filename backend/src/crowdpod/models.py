# Persona identity/behaviour split adapted from the upstream project listed in NOTICE (AGPL-3.0); modified 2026-10-30.
"""Data models shared by the pipeline, the store and the API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Verdict = Literal["adopt", "maybe", "reject"]
PricePeriod = Literal["one_time", "month", "year", "free"]
HandsAction = Literal["click", "type", "scroll", "back", "done", "give_up"]
HandsOutcome = Literal["success", "gave_up", "step_limit", "error"]
RunStatus = Literal["queued", "running", "finished", "failed"]

Range = tuple[float, float]


def inr(amount: float) -> str:
    """Rupees with Indian digit grouping: 189900 -> ₹1,89,900."""
    digits = str(abs(round(amount)))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        pairs = [head[max(i - 2, 0):i] for i in range(len(head), 0, -2)]
        digits = ",".join(reversed(pairs)) + "," + tail
    return ("-" if amount < 0 else "") + "₹" + digits


class IdeaBrief(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    pitch: str = Field(min_length=10, max_length=4000)
    category: str = Field(default="", max_length=80)
    price: float = Field(default=0, ge=0)
    currency: str = Field(default="INR", max_length=8)
    price_period: PricePeriod = "month"
    target_hint: str = Field(default="", max_length=600)
    url: str | None = None
    competitor_url: str | None = None

    @property
    def monthly_price(self) -> float:
        """Price spread over a month, so it can be compared with persona budgets."""
        if self.price_period == "free":
            return 0.0
        if self.price_period == "year":
            return round(self.price / 12, 2)
        if self.price_period == "one_time":
            return round(self.price / 12, 2)  # treated as a year of use
        return self.price

    @property
    def one_time(self) -> bool:
        return self.price_period == "one_time"

    @property
    def price_unit(self) -> Literal["one_time", "month"]:
        return "one_time" if self.one_time else "month"

    @property
    def basis_price(self) -> float:
        """The price in the terms a person weighs it: the whole amount for a one-off purchase
        (a phone, a laptop), per month for anything paid repeatedly."""
        return self.price if self.one_time else self.monthly_price

    def price_text(self, amount: float | None = None) -> str:
        amount = self.basis_price if amount is None else amount
        if self.price_period == "free" and amount == 0:
            return "free"
        return f"{inr(amount)} one-time" if self.one_time else f"{inr(amount)}/month"

    def text(self) -> str:
        return " ".join([self.name, self.category, self.pitch, self.target_hint]).lower()


class Dealbreaker(BaseModel):
    when: list[str]
    say: str


class Voice(BaseModel):
    adopt: list[str] = []
    maybe: list[str] = []
    reject: list[str] = []


class Archetype(BaseModel):
    """One persona note: handwritten in vault/personas/archetypes, or generated for an idea."""

    id: str
    label: str
    weight: float = 1.0
    names: list[str]
    gender: str = "any"
    age: Range
    profession: str
    city: str = ""
    budget_month: Range  # what they spend each month on apps and subscriptions
    purchase_budget: Range = (0, 0)  # what they'd spend on one big one-off purchase; 0 means 12x monthly
    patience_seconds: Range
    tech_comfort: Range
    price_sensitivity: Range
    sentiment_bias: Range
    moods: list[str]
    devices: list[str]
    mbti: list[str] = []
    interests: list[str] = []
    pains: list[str] = []
    objections: list[str] = []
    dealbreakers: list[Dealbreaker] = []
    goals_on_site: list[str] = ["find the price"]
    goal_keywords: list[str] = ["price", "pricing"]
    must_haves: list[str] = []
    voice: Voice = Voice()
    body: str = ""  # Markdown prose below the frontmatter
    source: str = ""  # path of the note, relative to the vault
    generated_for: str = ""  # the idea this persona was generated for; empty for handwritten ones
    evidence: list[str] = []  # research facts this persona is based on


class Persona(BaseModel):
    """One sampled member of a crowd. Identity fields first, behaviour fields after."""

    id: str
    archetype_id: str
    seed: int
    # identity
    name: str
    age: int
    gender: str
    profession: str
    city: str
    mbti: str
    # behaviour
    mood: str
    device: str
    budget_month: int
    purchase_budget: int = 0
    patience_seconds: int
    tech_comfort: float
    price_sensitivity: float
    sentiment_bias: float

    def budget_for(self, brief: IdeaBrief) -> int:
        """The budget to weigh this price against: one-off purchase money or monthly spend."""
        return self.purchase_budget if brief.one_time else self.budget_month

    def card(self, archetype: Archetype, brief: IdeaBrief | None = None) -> str:
        """Short description used when many personas share one model call."""
        money = (
            f"Can spend about ₹{self.purchase_budget:,} on a big one-off purchase"
            if brief is not None and brief.one_time
            else f"Spends about ₹{self.budget_month:,}/month on apps and subscriptions"
        )
        return (
            f"[{self.id}] {self.name}, {self.age}, {self.profession} ({archetype.label}), {self.city}. "
            f"Mood: {self.mood}. {money}. "
            f"Price sensitivity {self.price_sensitivity:.2f}, tech comfort {self.tech_comfort:.2f}, "
            f"optimism {self.sentiment_bias:+.2f}. Device: {self.device}. "
            f"Cares about: {', '.join(archetype.interests[:6])}. "
            f"Usual reasons to say no: {'; '.join(archetype.objections[:3])}."
        )


class Reaction(BaseModel):
    persona_id: str
    verdict: Verdict
    willingness_to_pay: float = Field(default=0, ge=0)
    sentiment: float = Field(default=0, ge=-1, le=1)
    quote: str = ""
    top_objection: str = ""
    must_have: str = ""
    reasoning: str = ""
    provider: str = ""

    @field_validator("verdict", mode="before")
    @classmethod
    def _norm_verdict(cls, v: Any) -> Any:
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("sentiment", mode="before")
    @classmethod
    def _clamp_sentiment(cls, v: Any) -> Any:
        try:
            return max(-1.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.0


class ReactionBatch(BaseModel):
    reactions: list[Reaction]


class SegmentStats(BaseModel):
    archetype_id: str
    label: str
    count: int
    adopt: int
    maybe: int
    reject: int
    adoption_rate: float
    interest_rate: float  # adopt + maybe
    avg_sentiment: float
    median_wtp: float
    price_fit_rate: float  # share whose budget covers the price
    score: float
    top_objections: list[tuple[str, int]]
    top_must_haves: list[tuple[str, int]]


class CrowdSummary(BaseModel):
    size: int
    monthly_price: float  # the price compared against budgets, in `price_unit` terms
    price_unit: Literal["one_time", "month"] = "month"
    adoption_rate: float
    interest_rate: float
    median_wtp: float
    median_wtp_interested: float  # among adopt + maybe; rejecters would pay nothing
    price_fit_rate: float
    best_segment: str | None
    worst_segment: str | None
    segments: list[SegmentStats]
    top_objections: list[tuple[str, int]]
    top_must_haves: list[tuple[str, int]]
    headline: str


class Documents(BaseModel):
    brd_md: str
    prd_md: str


# ---------------------------------------------------------------- research and generated audiences


def _bounded(data: Any, *, text: int, items: int, where: str) -> Any:
    """Reject oversized text and lists anywhere in user- or agent-supplied data."""
    if isinstance(data, str) and len(data) > text:
        raise ValueError(f"{where}: a text field is longer than {text} characters")
    if isinstance(data, (list, tuple)):
        if len(data) > items:
            raise ValueError(f"{where}: a list has more than {items} items")
        for v in data:
            _bounded(v, text=text, items=items, where=where)
    if isinstance(data, dict):
        for v in data.values():
            _bounded(v, text=text, items=items, where=where)
    return data


class Source(BaseModel):
    title: str = Field(default="", max_length=300)
    url: str = Field(max_length=2000)

    @field_validator("url")
    @classmethod
    def _web_only(cls, v: str) -> str:
        # rendered as a link in the UI: only real web addresses, never javascript: or data:
        parsed = __import__("urllib.parse", fromlist=["urlparse"]).urlparse(v.strip())
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("source links must be http:// or https:// addresses")
        return v.strip()


class Research(BaseModel):
    """What the brain learned about the idea's market before building the crowd."""

    summary: str
    facts: list[str] = []  # concrete findings, each ideally with a number
    price_points: list[str] = []  # what comparable products cost
    buyer_segments: list[str] = []  # who actually buys in this market
    sources: list[Source] = []
    grounded: bool = False  # True when it came from a live web search

    @model_validator(mode="before")
    @classmethod
    def _limits(cls, data: Any) -> Any:
        return _bounded(data, text=3000, items=30, where="research")


class GeneratedPersona(BaseModel):
    """One archetype the brain designs for this idea. Ranges are [low, high]."""

    id: str = Field(description="short kebab-case id, e.g. android-flagship-switcher")
    label: str = Field(description="who they are in 2-4 words, e.g. Android flagship switcher")
    share: float = Field(ge=0, le=1, description="estimated share of this idea's realistic market")
    profession: str
    city: str = ""
    names: list[str] = Field(min_length=3, description="6-10 common first names for people like this")
    age: Range
    budget_month: Range = Field(description="₹ per month they spend on apps and subscriptions")
    purchase_budget: Range = Field(description="₹ they would spend on one big one-off purchase like this one")
    patience_seconds: Range = Field(description="seconds they give a confusing website before leaving")
    tech_comfort: Range = Field(description="0 to 1")
    price_sensitivity: Range = Field(description="0 to 1")
    sentiment_bias: Range = Field(description="-1 to 1: how optimistic they are about new products")
    moods: list[str]
    devices: list[str] = Field(description="from: budget-android, mid-android, iphone, ipad, laptop, shared-tablet")
    interests: list[str] = Field(description="single lowercase words or short phrases")
    pains: list[str]
    objections: list[str] = Field(description="their realistic reasons to say no")
    must_haves: list[str]
    goals_on_site: list[str] = Field(description="what they would try to do on the product's website")
    who_they_are: str
    how_they_decide: str
    how_they_talk: str
    sample_quotes: list[str] = Field(description="3-5 things they might say about a product like this")
    evidence: list[str] = Field(description="research facts this persona is based on")

    @model_validator(mode="before")
    @classmethod
    def _limits(cls, data: Any) -> Any:
        return _bounded(data, text=600, items=20, where="persona")


class Audience(BaseModel):
    personas: list[GeneratedPersona] = Field(min_length=3, max_length=10)


class DescribedAudience(BaseModel):
    """The full personas for the people a user described, in the same order."""

    personas: list[GeneratedPersona] = Field(min_length=1, max_length=5)


class Observation(BaseModel):
    url: str
    title: str
    scroll_y: int
    scroll_max: int
    text: str
    elements: list[dict[str, Any]]
    content: str = ""  # visible text outside links and buttons

    def render(self, max_elements: int = 40) -> str:
        lines = [f"Page: {self.title} ({self.url})", f"Scrolled {self.scroll_y}px of {self.scroll_max}px."]
        lines.append("Visible text: " + self.text[:1200])
        lines.append("Things you can interact with:")
        for el in self.elements[:max_elements]:
            lines.append(f'- {el["id"]}: {el["role"]} "{el["label"]}"')
        return "\n".join(lines)


class HandsDecision(BaseModel):
    thought: str = ""
    action: HandsAction
    target: str = ""
    text: str = ""

    @field_validator("action", mode="before")
    @classmethod
    def _norm_action(cls, v: Any) -> Any:
        return v.strip().lower().replace(" ", "_") if isinstance(v, str) else v


class HandsStep(BaseModel):
    index: int
    t: float
    thought: str
    action: HandsAction
    target: str = ""
    target_label: str = ""
    text: str = ""
    url: str = ""
    screenshot: str = ""
    error: str = ""


class HandsSession(BaseModel):
    persona_id: str
    persona_name: str
    archetype_id: str
    url: str
    goal: str
    outcome: HandsOutcome
    seconds: float
    summary: str
    steps: list[HandsStep]


def _web_url(v: str) -> str:
    """Browser agents only visit web pages: no file://, javascript: or other schemes."""
    from urllib.parse import urlparse

    v = v.strip()
    parsed = urlparse(v)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("the website address must start with http:// or https://")
    return v


class HandsRequest(BaseModel):
    url: str
    personas: int = Field(default=5, ge=1, le=20)
    max_steps: int = Field(default=15, ge=1, le=60)
    archetypes: list[str] | None = None  # segments to send first; the rest are chosen automatically
    goal: str | None = Field(default=None, max_length=300)  # what every visitor tries to do
    goals: dict[str, str] | None = None  # per-segment goal; overrides `goal`

    @field_validator("url")
    @classmethod
    def _check_url(cls, v: str) -> str:
        return _web_url(v)

    def goal_for(self, archetype: Archetype) -> str:
        return (self.goals or {}).get(archetype.id) or self.goal or archetype.goals_on_site[0]


class RunRequest(BaseModel):
    brief: IdeaBrief
    crowd_size: int = Field(default=200, ge=1, le=5000)
    mix: dict[str, float] | None = None
    seed: int = 7
    hands: HandsRequest | None = None
    # generated = research the market and design personas for this idea (needs a model brain);
    # builtin = the handwritten archetypes; both = generated personas plus the handwritten ones
    audience: Literal["generated", "builtin", "both"] = "generated"
    audience_size: int = Field(default=6, ge=3, le=10)  # how many personas to generate
    context_notes: str = Field(default="", max_length=6000)  # what the founder already knows about the market
    # Personas and research supplied by the caller (e.g. an MCP client that did its own web search);
    # used instead of asking the brain to research and design them.
    provided_audience: Audience | None = None
    provided_research: Research | None = None
    # people the user describes in a sentence each ("a broke engineering student in Pune");
    # each becomes a full persona and a segment of the crowd
    described: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("described")
    @classmethod
    def _described(cls, v: list[str]) -> list[str]:
        out = [d.strip() for d in v if d.strip()]
        if any(len(d) > 400 for d in out):
            raise ValueError("describe each person in at most 400 characters")
        return out


class RunEvent(BaseModel):
    seq: int
    run_id: str
    type: str
    data: dict[str, Any] = {}
