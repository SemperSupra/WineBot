"""Offline source-contract checks for independent WinInspect corrective PRs."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class WinInspectContractTests(unittest.TestCase):
    def test_no_hello_payload_in_correlation_error(self):
        source = (ROOT / "api/core/wininspect.py").read_text()
        # The baseline is expected to be RED until PR 141 is reconciled.
        # This fixture is deliberately non-gating until the corrected source
        # is incorporated into the owning integration work cell.
        self.assertIn("response.get(\"id\") != request_id", source)

    def test_pinned_archive_candidate_is_separate_pr(self):
        docker = (ROOT / "docker/Dockerfile").read_text()
        self.assertIn("download_tool.sh \"WinInspect\"", docker)

if __name__ == "__main__":
    unittest.main()
