import copy
import unittest

from record_fixture import prepare_fixture, require_safe_request

VERSION = "a1111111-1111-4111-8111-111111111111"
RUN = "b2222222-2222-4222-8222-222222222222"
NODE = "c3333333-3333-4333-8333-333333333333"


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self.template = {
            "name": "workflows.runs.get.running",
            "description": "Synthetic run",
            "operation": "getWorkflowRun",
            "request": {"headers": {}},
            "response": {"status": 200},
            "expect": {"kind": "resource", "resource": {"status": "running"}},
        }
        self.exchange = {
            "request": {
                "method": "GET",
                "path": "/v1/workflow/runs/" + RUN,
                "headers": {},
            },
            "response": {
                "status": 200,
                "headers": {
                    "Location": "/v1/workflow/runs/" + RUN,
                    "Set-Cookie": "private",
                },
                "body": {
                    "data": {
                        "id": RUN,
                        "configVersionID": VERSION,
                        "status": "running",
                        "extra": {NODE: {"nodeId": NODE}},
                        "billing": {"amountUsd": "0.0090"},
                    },
                    "error": "",
                    "status": 200,
                    "errorCode": "",
                },
            },
        }
        self.source = {
            "from": "local synthetic HTTP recording",
            "recordedAt": "2026-11-13T00:00:00Z",
            "capture": "live-http",
        }

    def test_replaces_related_ids_and_drops_non_public_headers(self):
        fixture = prepare_fixture(self.template, self.exchange, self.source)
        data = fixture["response"]["body"]["data"]
        self.assertEqual(data["id"], "00000000-0000-4000-8000-000000000002")
        self.assertEqual(
            data["configVersionID"], "00000000-0000-4000-8000-000000000001"
        )
        self.assertTrue(fixture["request"]["path"].endswith(data["id"]))
        self.assertTrue(fixture["response"]["headers"]["Location"].endswith(data["id"]))
        node = next(iter(data["extra"]))
        self.assertEqual(data["extra"][node]["nodeId"], node)
        self.assertEqual(data["billing"]["amountUsd"], "0.0090")
        self.assertNotIn("Set-Cookie", fixture["response"]["headers"])
        self.assertEqual(self.exchange["response"]["body"]["data"]["id"], RUN)

    def test_in_progress_error_keeps_its_related_run_id(self):
        self.template["response"]["status"] = 409
        self.exchange["response"].update(
            status=409,
            body={
                "data": None,
                "error": "workflow request is already processing; inspect the original run: "
                + RUN,
                "errorCode": "",
                "status": 409,
            },
        )
        fixture = prepare_fixture(self.template, self.exchange, self.source)
        error = fixture["expect"]["error"]
        self.assertEqual(error["class"], "ConflictError")
        self.assertIn(error["existingRunId"], fixture["response"]["body"]["error"])
        self.assertEqual(error["errorCode"], "")

    def test_credentials_in_payload_or_metadata_are_refused(self):
        for location in ("body", "source"):
            exchange, source = copy.deepcopy(self.exchange), dict(self.source)
            if location == "body":
                exchange["response"]["body"]["error"] = "do-not-store-this-key"
            else:
                source["from"] = "do-not-store-this-key"
            with self.assertRaisesRegex(ValueError, "credential"):
                prepare_fixture(
                    self.template, exchange, source, secrets=("do-not-store-this-key",)
                )

    def test_wrong_http_or_lifecycle_status_cannot_replace_a_fixture(self):
        for change in ("http", "lifecycle"):
            exchange = copy.deepcopy(self.exchange)
            if change == "http":
                exchange["response"]["status"] = 404
            else:
                exchange["response"]["body"]["data"]["status"] = "succeeded"
            with self.assertRaises(ValueError):
                prepare_fixture(self.template, exchange, self.source)

    def test_failed_http_200_preserves_partial_json_and_empty_final_fallback(self):
        self.template["expect"] = {"kind": "outcome", "outcome": {"status": "failed"}}
        values = {"input": {"enabled": False, "count": 0, "value": None}, "final": {}}
        self.exchange["response"]["body"]["data"] = {
            "data": values,
            "error": "synthetic failure",
            "steps": [],
        }
        fixture = prepare_fixture(self.template, self.exchange, self.source)
        self.assertEqual(
            fixture["expect"]["outcome"],
            {
                "status": "failed",
                "error": "synthetic failure",
                "output": values,
                "stepCount": 0,
            },
        )

    def test_absolute_urls_and_credential_headers_are_refused(self):
        for path in (
            "https://other.example/v1/workflow/runs",
            "//other.example/v1/workflow/runs",
            "/v1/dashboard/api-keys",
        ):
            with self.assertRaises(ValueError):
                require_safe_request({"path": path})
        with self.assertRaises(ValueError):
            require_safe_request(
                {"path": "/v1/workflow/runs", "headers": {"Authorization": "private"}}
            )


if __name__ == "__main__":
    unittest.main()
