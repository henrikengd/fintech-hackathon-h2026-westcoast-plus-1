from datetime import date
import unittest

from pydantic import ValidationError

from voting_assistant.contracts import Agenda, Assessment, Guideline, Vote


SOURCE = {
    "document": "Synthetic meeting notice",
    "document_date": "2025-02-01",
    "version": "1",
    "sha256": "a" * 64,
    "page": 1,
}


class AgendaTests(unittest.TestCase):
    def test_rejects_duplicate_proposal_ids(self):
        proposal = {"proposal_id": "1", "original_text": "Elect a director", "sources": []}
        with self.assertRaisesRegex(ValidationError, "proposal_id must be unique"):
            Agenda.model_validate(
                {
                    "meeting_id": "m1",
                    "company_id": "c1",
                    "meeting_date": "2025-03-01",
                    "document_source": SOURCE,
                    "proposals": [proposal, proposal],
                }
            )

    def test_rejects_missing_document_source(self):
        with self.assertRaisesRegex(ValidationError, "document_source"):
            Agenda.model_validate(
                {
                    "meeting_id": "m1",
                    "company_id": "c1",
                    "meeting_date": "2025-03-01",
                    "proposals": [
                        {"proposal_id": "1", "original_text": "Elect a director", "sources": []}
                    ],
                }
            )


class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.assessment = {
            "proposal_id": "1",
            "status": "manual_review",
            "recommendation": None,
            "rationale": "The document omits board composition.",
            "policy_sources": [],
            "factual_sources": [],
            "missing_information": ["Board composition"],
            "uncertainty_reason": "Missing facts",
        }

    def test_rejects_invalid_status(self):
        with self.assertRaises(ValidationError):
            Assessment.model_validate(self.assessment | {"status": "pending"})

    def test_manual_review_requires_null_vote_and_reason(self):
        for invalid in ({"recommendation": "AVSTÅ"}, {"uncertainty_reason": " "}):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                Assessment.model_validate(self.assessment | invalid)
        self.assertIsNone(Assessment.model_validate(self.assessment).recommendation)

    def test_abstention_is_a_recommendation(self):
        result = Assessment.model_validate(
            self.assessment
            | {
                "status": "assessed",
                "recommendation": "AVSTÅ",
                "policy_sources": [SOURCE],
                "factual_sources": [SOURCE],
                "missing_information": [],
                "uncertainty_reason": None,
            }
        )
        self.assertEqual(result.recommendation, Vote.AVSTÅ)

    def test_recommendation_requires_sources(self):
        with self.assertRaisesRegex(ValidationError, "policy sources and factual sources"):
            Assessment.model_validate(
                self.assessment | {"status": "assessed", "recommendation": "MOT"}
            )


class GuidelineTests(unittest.TestCase):
    def test_policy_end_date_is_exclusive(self):
        guideline = Guideline.model_validate(
            {
                "guideline_id": "board",
                "text": "Illustrative board policy",
                "policy_version": "1",
                "valid_from": "2025-02-01",
                "valid_until": "2025-04-01",
                "section": "Board",
                "source": SOURCE,
            }
        )
        self.assertFalse(guideline.applies_on(date(2025, 1, 31)))
        self.assertTrue(guideline.applies_on(date(2025, 2, 1)))
        self.assertFalse(guideline.applies_on(date(2025, 4, 1)))
