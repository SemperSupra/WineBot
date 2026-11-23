"""Offline adversarial census regression. No GitHub/network/host mutation."""
import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/ci/check-remote-ref-census.py"
DATA = ROOT / "docs/reconciliation/r040-remote-ref-census-2026-11-23.json"
spec = importlib.util.spec_from_file_location("ref_census", SCRIPT)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class CensusValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = json.loads(DATA.read_text(encoding="utf-8"))

    def test_original_snapshot_coherent(self):
        result = checker.validate(copy.deepcopy(self.original))
        self.assertGreater(result["remote_branches"], 100)
        self.assertGreater(result["open_prs"], 40)

    def test_duplicate_ref_refused(self):
        data = copy.deepcopy(self.original)
        data["remote_branches"].append(copy.deepcopy(data["remote_branches"][0]))
        with self.assertRaises(ValueError):
            checker.validate(data)

    def test_wrong_count_refused(self):
        data = copy.deepcopy(self.original)
        data["counts"]["remote_branches"] += 1
        with self.assertRaises(ValueError):
            checker.validate(data)

    def test_wrong_pr_head_refused(self):
        data = copy.deepcopy(self.original)
        data["open_prs"][0]["head_sha"] = "a" * 40
        with self.assertRaises(ValueError):
            checker.validate(data)

    def test_unproven_branch_reclassification_refused(self):
        data = copy.deepcopy(self.original)
        name = next(b for b in data["remote_branches"]
                    if not b["open_pr_head"] and not b["open_pr_base"])
        name["open_pr_head"] = True
        with self.assertRaises(ValueError):
            checker.validate(data)

    def test_false_main_merge_refused(self):
        data = copy.deepcopy(self.original)
        data["feature_merge"]["protected_main_merged"] = True
        with self.assertRaises(ValueError):
            checker.validate(data)


if __name__ == "__main__":
    unittest.main()
