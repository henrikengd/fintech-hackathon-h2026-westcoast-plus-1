"""Validated boundaries between documents, retrieval, assessment and scoring."""

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
OriginalText = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class Vote(StrEnum):
    FOR = "FOR"
    MOT = "MOT"
    AVSTÅ = "AVSTÅ"


class Source(Contract):
    document: NonEmpty
    url: NonEmpty | None = None
    section: NonEmpty | None = None
    page: int | None = Field(default=None, ge=1)
    document_date: date
    version: NonEmpty
    sha256: Sha256
    quote: OriginalText | None = None


class Proposal(Contract):
    proposal_id: NonEmpty
    original_text: OriginalText
    sources: list[Source]
    proposal_type: NonEmpty | None = None


class Agenda(Contract):
    meeting_id: NonEmpty
    company_id: NonEmpty
    meeting_date: date
    document_source: Source
    proposals: list[Proposal] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_proposals(self) -> Self:
        ids = {proposal.proposal_id for proposal in self.proposals}
        if len(ids) != len(self.proposals):
            raise ValueError("proposal_id must be unique within an agenda")
        return self


class Guideline(Contract):
    guideline_id: NonEmpty
    text: OriginalText
    policy_version: NonEmpty
    valid_from: date
    valid_until: date | None = None
    section: NonEmpty
    source: Source

    @model_validator(mode="after")
    def valid_interval(self) -> Self:
        if self.valid_until is not None and self.valid_until <= self.valid_from:
            raise ValueError("valid_until must be after valid_from")
        return self

    def applies_on(self, as_of_date: date) -> bool:
        return self.valid_from <= as_of_date and (
            self.valid_until is None or as_of_date < self.valid_until
        )


class Assessment(Contract):
    proposal_id: NonEmpty
    status: Literal["assessed", "manual_review"]
    recommendation: Vote | None
    rationale: NonEmpty
    policy_sources: list[Source]
    factual_sources: list[Source]
    missing_information: list[NonEmpty]
    uncertainty_reason: NonEmpty | None

    @model_validator(mode="after")
    def check_status(self) -> Self:
        if self.status == "manual_review":
            if self.recommendation is not None or self.uncertainty_reason is None:
                raise ValueError("manual review requires a null recommendation and a reason")
        elif self.recommendation is None or not self.policy_sources or not self.factual_sources:
            raise ValueError("assessment requires a recommendation, policy sources and factual sources")
        return self


class ReferenceVote(Contract):
    proposal_id: NonEmpty
    vote: Vote | None
    board_recommendation: Vote | None = None
    raw_vote: str | None = None


class MeetingReference(Contract):
    meeting_id: NonEmpty
    source: Source
    vote_semantics: Literal["voting_intention", "cast_vote", "unverified", "synthetic"]
    votes: list[ReferenceVote]

    @model_validator(mode="after")
    def unique_votes(self) -> Self:
        if len({vote.proposal_id for vote in self.votes}) != len(self.votes):
            raise ValueError("proposal_id must be unique within meeting reference votes")
        return self
