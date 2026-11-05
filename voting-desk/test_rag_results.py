"""Aggregate-only results, matched comparison cohorts, and missing artifacts."""
import json
from pathlib import Path
import tempfile
import unittest

import rag_results


def metrics(n=10, precision=.5):
    return {"known_votes": n, "mot": 2, "precision": precision, "recall": .5, "f1": .5,
            "recommendation_coverage": .8, "manual_review_share": .2,
            "verified_rule_quote_coverage": .7, "verified_evidence_coverage": .9}


def report(attempted=1, completed=1, failed=0, pending=1):
    return {"data_id": "same", "cohort_meetings": 2, "runs": [{
        "mode": "hybrid", "strategy": "meeting", "attempted_meetings": attempted,
        "completed_meetings": completed, "failed_meetings": failed, "pending_meetings": pending,
        "metrics": metrics(), "same_rows_baselines": {"follow_board": metrics(10, .123)}}]}


def vector_summary(recall=.75, precision=.4):
    dev = {"n": 100, "mot": 20, "tp": 15, "fp": 22, "fn": 5, "precision": precision, "recall": recall, "f1": .52}
    return {"embedding_model": "BAAI/bge-small-en-v1.5", "embedding_dimension": 384, "api_calls": 0,
            "target_recall": .85, "development_period": "2024", "fit_period": "2019–2023",
            "selected_config": {"k": 10, "company_weight": 1}, "selected_threshold": .2,
            "validation_selected": {"n": 80, "mot": 10, "precision": .2, "recall": .9, "f1": .33},
            "development_selected": dev, "development_follow_board": dict(dev),
            "cached_claude_same_development": dict(dev), "local_text_same_development": dict(dev)}


def learning_summary(precision=.9, recall=.9):
    data = vector_summary(recall=recall, precision=precision)
    data.update(target_precision=.85, selected_config={"name": "Example model", "kind": "classifier"}, feature_count=10,
                local_vector_same_development=dict(data["development_selected"]))
    data["operating_points"] = [{"name": name, "threshold": value, "validation": dict(data["validation_selected"]),
                                 "development": dict(data["development_selected"])}
                                for name, value in (("balanced", .5), ("precision", .8), ("recall", .2))]
    data["validation_per_year"] = [{"year": 2023, **data["validation_selected"]}]
    return data


class ResultsRendering(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)

    def save(self, name, value):
        path = self.base / rag_results.ARTIFACTS[name][1]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_missing_and_malformed_artifacts_remain_readable(self):
        html = rag_results.render_body(self.base)
        self.assertIn("Ikke lagret ennå", html)
        self.assertIn("ikke en ny, uavhengig sluttest", html)
        path = self.base / rag_results.ARTIFACTS["rag"][1]
        path.parent.mkdir(parents=True)
        path.write_text("{unfinished", encoding="utf-8")
        self.assertIn("Kan ikke leses nå", rag_results.render_body(self.base))

    def test_partial_run_uses_its_same_rows_baseline_not_full_cohort(self):
        self.save("rag", report())
        self.save("baseline", {"data_id": "same", "meetings": 2, "methods": {"follow_board": metrics(99, .987)}})
        html = rag_results.render_body(self.base)
        self.assertIn("Foreløpige resultater", html)
        self.assertIn("12,3 %", html)
        self.assertNotIn("98,7 %", html)
        self.assertIn("1 / 2 møter fullført", html)
        self.assertIn("1 gjenstår", html)

    def test_full_cohort_shares_one_table_and_preserves_failed_call_status(self):
        self.save("rag", report(attempted=2, completed=1, failed=1, pending=0))
        self.save("baseline", {"data_id": "same", "meetings": 2, "methods": {"follow_board": metrics(20, .987)}})
        html = rag_results.render_body(self.base)
        self.assertIn("Samme utvalg på 2 møter", html)
        self.assertIn("98,7 %", html)
        self.assertIn("1 møter feilet", html)
        self.assertIn("falske negative", html)

    def test_different_dataset_never_uses_full_baseline(self):
        self.save("rag", report(attempted=2, completed=2, pending=0))
        self.save("baseline", {"data_id": "different", "meetings": 2, "methods": {"follow_board": metrics(99, .987)}})
        html = rag_results.render_body(self.base)
        self.assertIn("12,3 %", html)
        self.assertNotIn("98,7 %", html)

    def test_only_allowlisted_aggregates_are_rendered(self):
        data = report()
        data.update(api_key="SECRET_SENTINEL", bundle={"passages": ["RAW_DOCUMENT_SENTINEL"]})
        data["runs"][0]["metrics"]["raw_prompt"] = "PROMPT_SENTINEL"
        self.save("rag", data)
        self.save("retrieval", {"primary_questions": {
            "summary": {"hybrid": {"queries": 12, "anchor_hits_at_5": 9, "anchor_hit_at_5": .75,
                                    "mrr_at_5": .6, "source_quote_validity": 1}},
            "queries": [{"question": "QUESTION_SENTINEL", "quote": "QUOTE_SENTINEL"}]}})
        html = rag_results.render_body(self.base)
        for forbidden in ("SECRET_SENTINEL", "RAW_DOCUMENT_SENTINEL", "PROMPT_SENTINEL", "QUESTION_SENTINEL", "QUOTE_SENTINEL", "<script", "<form", "file://", "data/local-rag"):
            self.assertNotIn(forbidden, html)
        self.assertIn("12 manuelt kontrollerte", html)
        self.assertIn("75,0 %", html)
        self.assertIn("ufullstendige relevansvurderinger", html)

    def test_undefined_precision_is_not_rendered_as_zero(self):
        data = report()
        data["runs"][0]["metrics"]["precision"] = None
        self.save("rag", data)
        self.assertIn("<td>—</td>", rag_results.render_body(self.base))
        self.assertEqual(rag_results.percentage(float("nan")), "—")

    def test_table_escapes_text_and_classifier_is_a_separate_cohort(self):
        self.assertNotIn("<script>", rag_results.table(["<script>"], [["<script>"]], "<script>"))
        self.save("classifier", {"development_selected": {"n": 1505, "mot": 77, "precision": .38},
                                 "development_follow_board": {"n": 1505, "mot": 77, "precision": .42}})
        html = rag_results.render_body(self.base)
        self.assertIn("1505", html)
        self.assertIn("større utviklingsutvalg", html)
        self.assertIn("ikke sammenlignes direkte med RAG-tabellen", html)

    def test_injection_result_preserves_null_baseline_and_scope_limitations(self):
        self.save("injection", {"status": "completed", "proposals": 15, "vote_changes": 0,
                                "changed_to_attacker_target": 0, "marker_in_generated_text": False,
                                "full_requested_override_observed": False, "clean_all_predictions_null": True,
                                "payload": "RAW_ATTACK_SENTINEL"})
        html = rag_results.render_body(self.base)
        self.assertIn("Uendrede nullsvar", html)
        self.assertIn("etter dokumentsøket", html)
        self.assertIn("ikke en generell måling av robusthet", html)
        self.assertNotIn("RAW_ATTACK_SENTINEL", html)

    def test_new_board_target_precedes_historical_mot_and_vector_sections(self):
        html = rag_results.render_body(self.base)
        self.assertLess(html.index("<h2>Avvik fra styrets anbefaling"), html.index("<h2>Tidligere forsøk · MOT på forslaget"))
        self.assertLess(html.index("<h2>Tidligere forsøk · MOT på forslaget"), html.index("<h2>Tidligere forsøk · lokal vektormodell"))
        self.assertLess(html.index("<h2>Tidligere forsøk · lokal vektormodell"), html.index("<h2>Stemmeanbefalinger fra RAG"))
        self.assertIn("Resultatene fra den lokale vektormodellen er ikke lagret ennå", html)
        self.assertNotIn("er nådd på utviklingsutvalget", html)

    def test_vector_target_uses_development_measurement_not_optimistic_flag_or_validation(self):
        data = vector_summary()
        data["target_achieved_development"] = True
        self.save("vector", data)
        html = rag_results.render_body(self.base)
        self.assertIn("85,0 % er ikke nådd på utviklingsutvalget", html)
        self.assertIn("Målt recall er 75,0 %", html)
        self.assertIn("Validering brukt til modellvalg", html)
        self.assertIn("90,0 %", html)
        self.assertIn("samme 100 saker", html)
        self.assertIn("0 API-kall", html)
        self.assertIn("ikke FOR versus AVSTÅ", html)
        self.assertIn("ikke et kalibrert mål på sikkerhet", html)
        self.assertIn("Ulike terskler", html)

    def test_vector_target_met_is_reported_without_guaranteeing_new_cases(self):
        data = vector_summary(recall=.9)
        data["target_achieved_development"] = False
        html = rag_results.vector_section(data)
        self.assertIn("85,0 % er nådd på utviklingsutvalget", html)
        self.assertIn("ingen garanti for nye saker", html)

    def test_vector_zero_and_missing_values_stay_distinct(self):
        data = vector_summary(recall=0, precision=None)
        html = rag_results.vector_section(data)
        self.assertIn("Målt recall er 0,0 %", html)
        self.assertIn("<td>—</td>", html)
        data["development_selected"]["recall"] = None
        self.assertIn("Recall-målet kan ikke vurderes ennå", rag_results.vector_section(data))
        data["target_recall"] = 0
        data["development_selected"]["recall"] = 0
        self.assertIn("0,0 % er nådd på utviklingsutvalget", rag_results.vector_section(data))

    def test_vector_comparison_excludes_mismatched_cohort_and_raw_records(self):
        data = vector_summary()
        data["local_text_same_development"] = {"n": 999, "mot": 22, "precision": .987}
        data["raw_neighbors"] = ["VECTOR_RAW_SENTINEL"]
        data["embedding_model"] = "<script>unsafe()</script>"
        self.save("vector", data)
        html = rag_results.render_body(self.base)
        self.assertIn("annet antall saker", html)
        self.assertNotIn("98,7 %", html)
        self.assertNotIn("VECTOR_RAW_SENTINEL", html)
        self.assertNotIn("<script>", html)

    def test_learning_pending_states_both_strict_targets(self):
        html = rag_results.render_body(self.base)
        self.assertIn("Historisk MOT-mål", html)
        self.assertIn("precision strengt over 85,0 % og recall strengt over 85,0 %, samtidig", html)
        self.assertIn("Resultatene fra den lærte modellen er ikke lagret ennå", html)
        self.assertIn("Måloppnåelse er ikke vurdert", html)

    def test_learning_requires_both_scores_strictly_above_target(self):
        for precision, recall in ((.85, .9), (.9, .85), (.85, .85), (.84, 1), (1, .84)):
            with self.subTest(precision=precision, recall=recall):
                html = rag_results.learning_section(learning_summary(precision, recall))
                self.assertIn("Det historiske MOT-målet er ikke nådd", html)
        html = rag_results.learning_section(learning_summary(.85000001, .85000001))
        self.assertIn("Det historiske MOT-målet er nådd", html)
        self.assertIn("uavrundede verdiene", html)

    def test_learning_nonfinite_invalid_or_absent_scores_cannot_claim_success(self):
        for value in (None, float("nan"), float("inf"), -.1, 1.1, True):
            with self.subTest(value=value):
                html = rag_results.learning_section(learning_summary(precision=value))
                self.assertIn("Det historiske MOT-målet kan ikke vurderes", html)
                self.assertNotIn("Det historiske MOT-målet er nådd", html)
        data = learning_summary()
        data["target_recall"] = float("inf")
        self.assertIn("kan ikke vurderes", rag_results.learning_section(data))

    def test_learning_compares_only_known_same_cohort_and_keeps_operating_points_separate(self):
        data = learning_summary()
        data["cached_claude_same_development"] = {"n": 999, "mot": 2, "precision": .987}
        data["local_text_same_development"] = {"mot": 20, "precision": .986}
        data["operating_points"][0]["development"] = {"n": 99, "mot": 20, "precision": .985}
        html = rag_results.learning_section(data)
        self.assertNotIn("98,7 %", html)
        self.assertNotIn("98,6 %", html)
        self.assertNotIn("98,5 %", html)
        self.assertIn("annet eller ukjent datagrunnlag", html)
        self.assertIn("tre terskler for den samme lærte modellen, ikke tre modeller", html)
        self.assertIn("Validering og utvikling holdes atskilt", html)
        self.assertIn("Prioriter precision", html)
        self.assertIn("Prioriter recall", html)

    def test_learning_escapes_metadata_and_never_renders_unselected_raw_fields(self):
        data = learning_summary()
        data["selected_config"]["name"] = "<script>attack()</script>"
        data["development_period"] = "<img src=x>"
        data["raw_training_labels"] = "LEARNING_RAW_SENTINEL"
        data["operating_points"][0]["threshold"] = None
        self.save("learning", data)
        html = rag_results.render_body(self.base)
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img src", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("LEARNING_RAW_SENTINEL", html)
        self.assertIn("Reserverte testmøter inngår ikke", html)

    def test_learning_uses_v2_only_and_explains_dynamic_reference_warmup(self):
        previous = self.base / "vote-learning-v1/summary.json"
        previous.parent.mkdir(parents=True)
        previous.write_text(json.dumps(learning_summary(.987, .987)), encoding="utf-8")
        pending = rag_results.render_body(self.base)
        self.assertIn("Resultatene fra den lærte modellen er ikke lagret ennå", pending)
        self.assertNotIn("98,7 %", pending)
        data = learning_summary()
        data.update(fit_period="2020–2023", reference_period="2019–2023", warmup_year=2019)
        data["validation_per_year"] = [{"year": year, **data["validation_selected"]} for year in (2021, 2022, 2023)]
        self.save("learning", data)
        html = rag_results.render_body(self.base)
        self.assertIn("År brukt til å trene klassifikatoren: 2020–2023", html)
        self.assertIn("Historiske referansesaker: 2019–2023", html)
        self.assertIn("Oppstartsåret 2019 brukes bare som historisk referanse", html)
        self.assertIn("Valideringsår: 2021, 2022, 2023", html)
        self.assertNotIn("98,7 %", html)
        self.assertTrue(previous.exists())
        data.update(reference_period="2018–2023", warmup_year=2018)
        self.assertIn("Oppstartsåret 2018", rag_results.learning_section(data))

    def test_learning_source_fact_direction_is_not_presented_as_measured_improvement(self):
        html = rag_results.learning_section(learning_summary())
        self.assertIn("En annen terskel tilfører ikke disse opplysningene", html)
        self.assertIn("ikke dokumentert forbedring", html)
        self.assertIn('href="/">Utforsk kildedokumentene', html)

    def test_board_artifact_is_read_from_the_same_fixed_base_and_header_is_target_safe(self):
        self.save("board", {"target": "against_board", "positive_class": "NBIM != mgmt_rec",
                            "fit_period": "2019–2023", "calibration_period": "2024", "test_period": "2025–2026",
                            "test_evaluated": False, "calibration_selected": {"n": 100, "positive": 20, "precision": .6, "recall": .5}})
        html = rag_results.render_body(self.base)
        self.assertIn("samme 100 kalibreringssaker", html)
        self.assertIn("Kalibrering og utviklingsmålinger", html)
        self.assertIn("Det aktive målet er høyest F1 for avvik fra styrets anbefaling", html)
        self.assertIn("MOT-precision og MOT-recall er ikke definert for denne binære modellen", html)
        self.assertNotIn("Reserverte testmøter er holdt utenfor de nye forsøkene", html)


if __name__ == "__main__":
    unittest.main()
