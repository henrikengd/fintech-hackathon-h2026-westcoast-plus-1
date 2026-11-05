"""Regression checks for pooled meeting splits. Run with: python test_dataset.py."""
import boot  # noqa: F401
import csv
from pathlib import Path
import tempfile
import unittest

import pandas as pd

import dataset
import desk


COLUMNS = [
    "injection_flag", "meeting_id", "company_id", "company", "ticker", "country",
    "market", "meeting_date", "item_no", "proposal_number", "proposal_text",
    "proponent", "mgmt_rec_raw", "nbim_vote_raw", "mgmt_rec", "nbim_vote",
    "against_board", "rationale_text", "position_paper", "year", "proposal_type",
    "rationale_section",
]


def fixture_rows():
    rows = []
    for year in (2023, 2024, 2025):
        for company in range(10):
            for item in ("1", "2"):
                vote = "MOT" if company % 2 and item == "1" else "FOR"
                rows.append({
                    "injection_flag": "0",
                    "meeting_id": f"{year}-{company}",
                    "company_id": str(company),
                    "company": f"Company {company}",
                    "ticker": f"C{company}",
                    "country": "Norway",
                    "market": "DM",
                    "meeting_date": f"{year}-06-{company + 1:02d}",
                    "item_no": item,
                    "proposal_number": item,
                    "proposal_text": f"Elect Director Person {item}",
                    "proponent": "Management",
                    "mgmt_rec_raw": "For",
                    "nbim_vote_raw": "Against" if vote == "MOT" else "For",
                    "mgmt_rec": "FOR",
                    "nbim_vote": vote,
                    "against_board": "1.0" if vote == "MOT" else "0.0",
                    "rationale_text": "",
                    "position_paper": "",
                    "year": str(year),
                    "proposal_type": "DIRECTOR_ELECTION",
                    "rationale_section": "",
                })
        # Two meeting IDs at the same company on the same day must stay together.
        extra = next(row.copy() for row in rows if row["meeting_id"] == f"{year}-0")
        extra["meeting_id"] += "-extra"
        rows.append(extra)
    return rows


def write_source(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def assignments(parts):
    return {
        (str(row.meeting_id), str(row.item_no)): name
        for name, frame in parts.items()
        for row in frame.itertuples()
    }


class PooledSplit(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.source = self.root / "votes.csv"
        self.output = self.root / "mixed"
        self.rows = fixture_rows()
        write_source(self.source, self.rows)

    def output_bytes(self):
        return {path.name: path.read_bytes() for path in self.output.iterdir()}

    def test_all_rows_are_preserved_and_related_meetings_stay_together(self):
        parts = dataset.split_source(self.source)
        self.assertEqual(set(parts), {"train", "test"})
        self.assertEqual(len(assignments(parts)), len(self.rows))
        self.assertEqual(sum(len(frame) for frame in parts.values()), len(self.rows))
        group_sets = {}
        for name, frame in parts.items():
            self.assertEqual(set(frame["split"]), {name})
            self.assertEqual(set(frame["meeting_date"].str[:4]), {"2023", "2024", "2025"})
            group_sets[name] = set(zip(frame["company_id"], frame["meeting_date"]))
        self.assertFalse(group_sets["train"] & group_sets["test"])
        combined = pd.concat(parts.values()).drop(columns="split")
        expected = pd.read_csv(self.source, dtype=str, keep_default_na=False)
        sort = ["meeting_id", "item_no"]
        pd.testing.assert_frame_equal(
            combined.sort_values(sort).reset_index(drop=True)[COLUMNS],
            expected.sort_values(sort).reset_index(drop=True)[COLUMNS],
        )

    def test_seed_is_repeatable_independent_of_source_row_order(self):
        expected = assignments(dataset.split_source(self.source, seed=2026))
        self.assertEqual(expected, assignments(dataset.split_source(self.source, seed=2026)))
        reordered = self.root / "reordered.csv"
        write_source(reordered, list(reversed(self.rows)))
        self.assertEqual(expected, assignments(dataset.split_source(reordered, seed=2026)))
        self.assertNotEqual(expected, assignments(dataset.split_source(self.source, seed=2027)))

    def test_split_allocates_80_20_within_each_year_and_vote_stratum(self):
        parts = dataset.split_source(self.source)
        for name, expected_groups in (("train", 4), ("test", 1)):
            groups = parts[name].groupby(["company_id", "meeting_date"]).agg(
                year=("year", "first"),
                has_mot=("nbim_vote", lambda votes: (votes == "MOT").any()),
            )
            strata = groups.groupby(["year", "has_mot"]).size()
            self.assertEqual(len(strata), 6)
            self.assertTrue((strata == expected_groups).all())

    def test_ambiguous_or_contaminated_source_rows_are_rejected(self):
        conflicting = self.rows[0].copy()
        conflicting["nbim_vote"] = "MOT"
        cases = {
            "duplicate key": self.rows + [conflicting],
            "injected row": [{**self.rows[0], "injection_flag": "1"}] + self.rows[1:],
            "unknown vote": [{**self.rows[0], "nbim_vote": "MAYBE"}] + self.rows[1:],
        }
        for name, rows in cases.items():
            with self.subTest(name=name):
                write_source(self.source, rows)
                with self.assertRaises(ValueError):
                    dataset.split_source(self.source)

    def test_repeated_build_reuses_identical_output(self):
        first = dataset.build_dataset(self.source, self.output)
        before = self.output_bytes()
        second = dataset.build_dataset(self.source, self.output)
        self.assertEqual(first, second)
        self.assertEqual(before, self.output_bytes())

    def test_changed_seed_or_source_cannot_replace_an_existing_dataset(self):
        dataset.build_dataset(self.source, self.output)
        before = self.output_bytes()
        with self.assertRaises(ValueError):
            dataset.build_dataset(self.source, self.output, seed=2027)
        self.assertEqual(before, self.output_bytes())
        changed = [row.copy() for row in self.rows]
        changed[0]["proposal_text"] = "Elect Director Another Person"
        write_source(self.source, changed)
        with self.assertRaises(ValueError):
            dataset.build_dataset(self.source, self.output)
        self.assertEqual(before, self.output_bytes())

    def test_invalid_output_and_input_directory_are_preserved(self):
        self.output.mkdir()
        marker = self.output / "keep.txt"
        marker.write_text("existing work", encoding="utf-8")
        with self.assertRaises(ValueError):
            dataset.build_dataset(self.source, self.output)
        self.assertEqual(marker.read_text(encoding="utf-8"), "existing work")
        original = self.source.read_bytes()
        with self.assertRaises(ValueError):
            dataset.build_dataset(self.source, self.root)
        self.assertEqual(original, self.source.read_bytes())

    def test_loader_detects_modified_output(self):
        dataset.build_dataset(self.source, self.output)
        path = self.output / "test.csv"
        path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaises(ValueError):
            dataset.load_split(self.output)

    def test_loader_detects_changed_canonical_source(self):
        dataset.build_dataset(self.source, self.output)
        self.source.write_bytes(self.source.read_bytes() + b"\n")
        with self.assertRaises(ValueError):
            dataset.load_split(self.output)

    def test_loader_keeps_mixed_assignments_and_training_history_excludes_test(self):
        dataset.build_dataset(self.source, self.output)
        parts = dataset.load_split(self.output)
        self.assertEqual(assignments(parts), assignments(dataset.split_source(self.source)))
        for name, frame in parts.items():
            self.assertEqual(set(frame["split"]), {name})
            self.assertEqual(set(frame["date"].dt.year), {2023, 2024, 2025})
            self.assertTrue({"person", "against", "voted"} <= set(frame.columns))
        train, test = parts["train"], parts["test"]
        test_keys = set(zip(test["meeting_id"], test["item_no"]))
        for company, date in test.groupby(["company_id", "date"]).groups:
            past = desk.history(train, company, date)
            self.assertFalse(set(zip(past["meeting_id"], past["item_no"])) & test_keys)
            self.assertTrue((past["date"] < date - desk.LAG).all())


if __name__ == "__main__":
    unittest.main()
