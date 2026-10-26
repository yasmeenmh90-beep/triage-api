"""The contract. Written from JOB-CARD.md before any model call exists."""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Category(str, Enum):
    billing = "billing"
    technical = "technical"
    account = "account"
    sales = "sales"
    other = "other"


class Urgency(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class Team(str, Enum):
    finance = "finance"
    engineering = "engineering"
    customer_success = "customer_success"
    sales = "sales"
    manual_review = "manual_review"


# An exact mapping is a lookup, not a judgement — so code does it, not the model.
TEAM_FOR_CATEGORY: dict[Category, Team] = {
    Category.billing: Team.finance,
    Category.technical: Team.engineering,
    Category.account: Team.customer_success,
    Category.sales: Team.sales,
    Category.other: Team.manual_review,
}


class TriageRequest(BaseModel):
    """What callers send us. Validated before we spend a model call."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2000)


class ModelVerdict(BaseModel):
    """Exactly what the model is allowed to return. Anything else is a failure."""

    model_config = ConfigDict(extra="forbid")

    category: Category
    urgency: Urgency
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=200)


class TriageResponse(ModelVerdict):
    """What our endpoint returns: the model's verdict plus the team chosen by code."""

    suggested_team: Team

    @classmethod
    def from_verdict(cls, verdict: ModelVerdict) -> "TriageResponse":
        return cls(**verdict.model_dump(), suggested_team=TEAM_FOR_CATEGORY[verdict.category])


STUB_VERDICT = ModelVerdict(
    category=Category.technical,
    urgency=Urgency.medium,
    confidence=0.9,
    reason="Stub mode: fixed response, no model was called.",
)
