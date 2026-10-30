# Persona identity/behaviour split adapted from the upstream project listed in NOTICE (AGPL-3.0); modified 2026-10-30.
"""Data models shared by the pipeline, the store and the API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

Verdict = Literal["adopt", "maybe", "reject"]
PricePeriod = Literal["one_time", "month", "year", "free"]
HandsAction = Literal["click", "type", "scroll", "back", "done", "give_up"]
HandsOutcome = Literal["success", "gave_up", "step_limit", "error"]
RunStatus = Literal["queued", "running", "finished", "failed"]

Range = tuple[float, float]


class IdeaBrief(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    pitch: str = Field(min_length=10, max_length=4000)
    category: str = ""
    price: float = Field(default=0, ge=0)
    currency: str = "INR"
    price_period: PricePeriod = "month"
    target_hint: str = ""
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
    """One handwritten persona note from vault/personas/archetypes."""

    id: str
    label: str
    weight: float = 1.0
    names: list[str]
    gender: str = "any"
    age: Range
    profession: str
    city: str = ""
    budget_month: Range
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
    patience_seconds: int
    tech_comfort: float
    price_sensitivity: float
    sentiment_bias: float

    def card(self, archetype: Archetype) -> str:
        """Short description used when many personas share one model call."""
        return (
            f"[{self.id}] {self.name}, {self.age}, {self.profession} ({archetype.label}), {self.city}. "
            f"Mood: {self.mood}. Budget for apps: about ₹{self.budget_month}/month. "
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
    monthly_price: float
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


class Observation(BaseModel):
    url: str
    title: str
    scroll_y: int
    scroll_max: int
    text: str
    elements: list[dict[str, Any]]

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


class HandsRequest(BaseModel):
    url: str
    personas: int = Field(default=5, ge=1, le=20)
    max_steps: int = Field(default=15, ge=1, le=60)
    archetypes: list[str] | None = None  # segments to send first; the rest are chosen automatically
    goal: str | None = Field(default=None, max_length=300)  # what every visitor tries to do
    goals: dict[str, str] | None = None  # per-segment goal; overrides `goal`

    def goal_for(self, archetype: Archetype) -> str:
        return (self.goals or {}).get(archetype.id) or self.goal or archetype.goals_on_site[0]


class RunRequest(BaseModel):
    brief: IdeaBrief
    crowd_size: int = Field(default=200, ge=1, le=5000)
    mix: dict[str, float] | None = None
    seed: int = 7
    hands: HandsRequest | None = None


class RunEvent(BaseModel):
    seq: int
    run_id: str
    type: str
    data: dict[str, Any] = {}
