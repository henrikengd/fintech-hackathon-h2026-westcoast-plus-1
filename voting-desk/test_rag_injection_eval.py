"""No-network tests for a paired, immutable generation-context injection experiment."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import rag_eval
import rag_injection_eval as attack


class InjectionExperiment(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.clean = self.root / "clean"
        self.output = self.root / "attacked"
        self.bundle = {"query_mode": "hybrid", "meeting": {"meeting_id": "1818232", "meeting_date": "2024-03-20"},
                       "proposals": [{"item": "1", "chunk_ids": ["source-a"]}],
                       "rules": [{"id": "rule-a", "quote": "Support independent directors."}],
                       "passages": [{"id": "source-a", "document_id": "doc-a", "url": "https://www.sec.gov/source", "filed": "2024-01-26",
                                     "text": "The director is independent.", "start": 0, "end": 28, "heading": "Board"}]}
        self.item = {"item": "1", "vote": "FOR", "rule_id": "rule-a", "rule_quote": "Support independent directors.",
                     "why": "The source states independence.", "missing_facts": [],
                     "evidence": [{"chunk_id": "source-a", "quote": "The director is independent."}]}
        self.settings = rag_eval.generation_settings()
        self.record = {"meeting_id": "1818232", "data_id": "fixture", "created_at": "2026-11-05T12:00:00+00:00", "settings": self.settings,
                       "status": "completed", "bundle": self.bundle, "result": {"items": [self.item]}}
        self.record["cache_key"] = rag_eval.fingerprint({"data_id": "fixture", "bundle": self.bundle, "settings": self.settings})
        self.path = self.clean / "cache/hybrid/config/1818232/clean.json"
        rag_eval.immutable_json(self.path, self.record)
        rag_eval.immutable_json(self.clean / "dataset.json", {"data_id": "fixture", "meetings": [self.bundle["meeting"]]})

    def client(self, item=None):
        raw = {"stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps({"items": [item or self.item]})}],
               "usage": {"input_tokens": 100, "output_tokens": 50}}
        create = Mock(return_value=SimpleNamespace(model_dump=lambda: raw))
        return SimpleNamespace(messages=SimpleNamespace(create=create))

    def test_attack_is_source_content_and_does_not_mutate_clean_data(self):
        before = deepcopy(self.bundle)
        prepared = attack.prepare(self.clean)
        self.assertEqual(self.bundle, before)
        self.assertEqual(json.loads(self.path.read_text())["bundle"], before)
        self.assertEqual(prepared["bundle"]["passages"][-1]["text"], attack.PAYLOAD)
        self.assertEqual(prepared["bundle"]["rules"], before["rules"])
        self.assertEqual(prepared["bundle"]["proposals"][0]["chunk_ids"][-1], prepared["bundle"]["passages"][-1]["id"])

    def test_settings_or_cache_drift_is_rejected_before_any_request(self):
        with patch.object(rag_eval, "generation_settings", return_value={**self.settings, "model": "different"}):
            with self.assertRaises(ValueError):
                attack.prepare(self.clean)
        record = json.loads(self.path.read_text())
        record["bundle"]["proposals"][0]["item"] = "changed"
        self.path.write_text(json.dumps(record))
        with self.assertRaises(ValueError):
            attack.prepare(self.clean)

    def test_success_preserves_raw_usage_and_reuses_cache_without_second_call(self):
        client = self.client()
        first = attack.run(self.clean, self.output, client=client)
        second = attack.run(self.clean, self.output, client=client)
        client.messages.create.assert_called_once()
        self.assertEqual(first, second)
        self.assertTrue(first["attacker_paragraph_supplied"])
        self.assertEqual(first["usage"], {"input_tokens": 100, "output_tokens": 50})
        self.assertEqual(first["comparison"]["vote_changes"], [])
        # The marker exists in the request, but must not be mistaken for marker obedience.
        self.assertFalse(first["comparison"]["marker_in_generated_text"])
        self.assertFalse(first["comparison"]["full_requested_override_observed"])

    def test_attack_compliance_and_missing_citations_are_measured(self):
        item = {**self.item, "vote": "MOT", "rule_id": None, "rule_quote": None, "evidence": [], "why": attack.MARKER}
        result = attack.run(self.clean, self.output, client=self.client(item))
        comparison = result["comparison"]
        self.assertEqual(comparison["changed_to_attacker_target"], 1)
        self.assertEqual(comparison["quote_changes"][0]["clean"]["rule_quote"], self.item["rule_quote"])
        self.assertIsNone(comparison["quote_changes"][0]["attacked"]["rule_quote"])
        self.assertTrue(comparison["full_requested_override_observed"])
        self.assertEqual(comparison["attacked_citation_omissions"], {"without_rule": 1, "without_evidence": 1})

    def test_failed_requests_are_cached_without_exception_secrets(self):
        client = self.client()
        client.messages.create.side_effect = RuntimeError("SECRET_CREDENTIAL_IN_EXCEPTION")
        first = attack.run(self.clean, self.output, client=client)
        attack.run(self.clean, self.output, client=client)
        client.messages.create.assert_called_once()
        self.assertEqual(first["status"], "failed")
        self.assertNotIn("SECRET", json.dumps(first))
        self.assertNotIn("comparison", first)

    def test_started_request_without_response_is_not_retried(self):
        prepared = attack.prepare(self.clean)
        rag_eval.immutable_json(self.output / f"{prepared['cache_key']}.started.json", {"started": True})
        client = self.client()
        with self.assertRaises(FileExistsError):
            attack.run(self.clean, self.output, client=client)
        client.messages.create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
