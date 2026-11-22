import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import validate_repo


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.operations = validate_repo.check_contract(validate_repo.Report())
        self.fixture = json.loads(
            (
                validate_repo.FIXTURES_DIR / "workflows/execute/succeeded.json"
            ).read_text()
        )

    def check_fixture(self, fixture):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixtures = root / "fixtures"
            fixtures.mkdir()
            (fixtures / "case.json").write_text(json.dumps(fixture))
            with patch.multiple(validate_repo, ROOT=root, FIXTURES_DIR=fixtures):
                report = validate_repo.Report()
                validate_repo.check_fixtures(report, self.operations)
                return report

    def test_recording_requires_timestamp_capture_method_and_server_contract(self):
        for field, invalid in (
            ("recordedAt", None),
            ("recordedAt", "2026-11-13"),
            ("capture", []),
            ("serverSpecSha256", None),
        ):
            fixture = copy.deepcopy(self.fixture)
            fixture["source"][field] = invalid
            self.assertTrue(self.check_fixture(fixture).errors, field)
        self.assertFalse(self.check_fixture(self.fixture).errors)

    def test_derived_fixture_remains_derived_and_visible(self):
        self.fixture["source"] = {"kind": "derived", "from": "handler code"}
        report = self.check_fixture(self.fixture)
        self.assertFalse(report.errors)
        self.assertTrue(any("derived" in warning for warning in report.warnings))

    def test_internal_implementation_terms_are_rejected_in_public_descriptions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = root / "contract"
            contract.mkdir()
            for path in validate_repo.CONTRACT_DIR.glob("*.json"):
                (contract / path.name).write_bytes(path.read_bytes())
            spec_path = contract / "openapi.json"
            spec = json.loads(spec_path.read_text())
            spec["paths"]["/v1/workflow/runs"]["post"]["summary"] = (
                "Dispatch an internal goroutine"
            )
            spec_path.write_text(json.dumps(spec))
            with patch.multiple(validate_repo, ROOT=root, CONTRACT_DIR=contract):
                report = validate_repo.Report()
                validate_repo.check_contract(report)
            self.assertTrue(
                any("internal term 'goroutine'" in error for error in report.errors)
            )


if __name__ == "__main__":
    unittest.main()
