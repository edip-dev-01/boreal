import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import COOKIE_NAME, create_app
from app.fixtures import load_fixtures
from app.query import freshness_of, parse_bbox
from app.repository import MemoryRepository

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
AS_OF = datetime(2026, 10, 11, 12, tzinfo=timezone.utc)
CANARY = "NIMBUS-RESTRICTED-CANARY-947"
RESTRICTED_IDS = ("fac-canary-annex", "src-restricted-register", "src-restricted-memo", "report-alder-restricted", "report-annex-restricted")


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.repository = MemoryRepository(load_fixtures(FIXTURES))
        self.app = create_app(self.repository, testing=True, as_of=AS_OF)
        self.client = TestClient(self.app)
        self.origin = {"Origin": "http://testserver"}

    def login(self, role="reader"):
        response = self.client.post("/api/login", json={"role": role}, headers=self.origin)
        self.assertEqual(response.status_code, 200, response.text)
        return {**self.origin, "X-CSRF-Token": response.json()["csrf_token"]}

    def assert_no_restricted(self, response):
        self.assertNotIn(CANARY, response.text)
        for forbidden in RESTRICTED_IDS:
            self.assertNotIn(forbidden, response.text)

    def test_unauthenticated_and_forged_sessions_are_denied(self):
        self.assertEqual(self.client.get("/api/session").json(), {"authenticated": False})
        for endpoint in ("/api/records", "/api/map", "/api/search", "/api/counts", "/api/records/fac-alder-library", "/api/sources/src-civic"):
            for headers in ({}, {"X-Role": "analyst", "Authorization": "Bearer analyst"}):
                self.assertEqual(self.client.get(endpoint, headers=headers).status_code, 401)
        self.client.cookies.set(COOKIE_NAME, "analyst")
        self.assertEqual(self.client.get("/api/records?role=analyst").status_code, 401)
        self.assertEqual(self.client.post("/api/ask", json={"question": "count facilities"}, headers=self.origin).status_code, 401)

    def test_reader_isolation_across_every_output_surface(self):
        headers = self.login()
        for endpoint in ("/api/records", "/api/map", "/api/search", "/api/counts", "/api/sources/src-civic"):
            response = self.client.get(endpoint)
            self.assertEqual(response.status_code, 200, response.text)
            self.assert_no_restricted(response)
        records = self.client.get("/api/records").json()["records"]
        self.assertEqual(len(records), 11)
        for record in records:
            response = self.client.get(f"/api/records/{record['id']}")
            self.assertEqual(response.status_code, 200)
            self.assert_no_restricted(response)
            for source in response.json()["sources"]:
                source_response = self.client.get(source["url"])
                self.assertEqual(source_response.status_code, 200)
                self.assert_no_restricted(source_response)
        for question in ("count facilities", "stale facilities", "conflicting reports", "missing coordinates", CANARY):
            response = self.client.post("/api/ask", json={"question": question}, headers=headers)
            self.assertEqual(response.status_code, 200)
            self.assert_no_restricted(response)
        for endpoint in ("/api/records/fac-canary-annex", "/api/sources/src-restricted-register", "/api/sources/src-restricted-memo"):
            response = self.client.get(endpoint)
            self.assertEqual(response.status_code, 404)
            self.assert_no_restricted(response)
        self.assertEqual(self.client.get("/api/records/fac-canary-annex").json(), self.client.get("/api/records/nonexistent").json())
        for endpoint in ("/api/records", "/api/search", "/api/counts", "/api/map"):
            response = self.client.get(endpoint, params={"q": CANARY})
            self.assertEqual(response.json()["count"], 0)
            self.assert_no_restricted(response)
        # A public facility has restricted nested content. Even the derived conflict
        # flag/source count must be computed from visible observations only.
        library = self.client.get("/api/records/fac-alder-library").json()
        self.assertFalse(library["conflict"])
        self.assertEqual(library["source_ids"], ["src-civic"])
        self.assertEqual(library["reports"], [])
        hall = self.client.get("/api/records/fac-meadow-hall").json()
        self.assertEqual([link["record_id"] for link in hall["links"]], ["fac-alder-library"])

    def test_analyst_sees_authorized_canary_and_nested_evidence(self):
        self.login("analyst")
        response = self.client.get("/api/records")
        self.assertEqual(response.json()["count"], 12)
        self.assertIn(CANARY, response.text)
        library = self.client.get("/api/records/fac-alder-library")
        self.assertIn(CANARY, library.text)
        self.assertTrue(library.json()["conflict"])
        self.assertEqual(len(library.json()["reports"]), 1)
        self.assertEqual(self.client.get("/api/sources/src-restricted-memo").status_code, 200)
        self.assertEqual(self.client.get("/api/counts").json()["conflicts"], 2)

    def test_query_or_headers_cannot_escalate_reader(self):
        self.login()
        response = self.client.get("/api/records?role=analyst", headers={"X-Role": "analyst", "X-Demo-Role": "analyst"})
        self.assertEqual(response.json()["count"], 11)
        self.assert_no_restricted(response)
        response = self.client.post("/api/login", json={"role": "admin"}, headers=self.origin)
        self.assertEqual(response.status_code, 422)
        response = self.client.post("/api/login", json={"role": "analyst", "user_id": "forged"}, headers=self.origin)
        self.assertEqual(response.status_code, 422)

    def test_cookie_security_session_rotation_logout_and_expiry(self):
        response = self.client.post("/api/login", json={"role": "reader"}, headers=self.origin)
        cookie = response.headers["set-cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=strict", cookie)
        self.assertIn("Path=/api", cookie)
        old = self.client.cookies.get(COOKIE_NAME)
        self.assertGreaterEqual(len(old), 40)
        self.assertNotIn("reader", old)
        headers = self.login("analyst")
        self.assertIsNone(self.app.state.sessions.get(old))
        self.assertEqual(self.client.get("/api/session").json()["role"], "analyst")
        response = self.client.post("/api/logout", headers=headers)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.client.get("/api/session").json(), {"authenticated": False})
        self.assertEqual(self.client.get("/api/records").status_code, 401)
        self.login()
        with patch("app.api.time.monotonic", return_value=10**12):
            self.assertEqual(self.client.get("/api/records").status_code, 401)

    def test_origin_host_and_csrf_validation(self):
        for origin in ({}, {"Origin": "https://evil.example"}, {"Origin": "null"}, {"Origin": "http://testserver", "Sec-Fetch-Site": "cross-site"}):
            self.assertEqual(self.client.post("/api/login", json={"role": "reader"}, headers=origin).status_code, 403)
        self.assertEqual(self.client.get("/api/session", headers={"host": "evil.example"}).status_code, 400)
        good = self.login()
        for endpoint, payload in (("/api/logout", None), ("/api/ask", {"question": "count facilities"})):
            self.assertEqual(self.client.post(endpoint, json=payload, headers=self.origin).status_code, 403)
            self.assertEqual(self.client.post(endpoint, json=payload, headers={**self.origin, "X-CSRF-Token": "wrong"}).status_code, 403)
            self.assertEqual(self.client.post(endpoint, json=payload, headers={**good, "Origin": "https://evil.example"}).status_code, 403)
        response = self.client.post("/api/ask", json={"question": "count facilities"}, headers=good)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        invalid = self.client.post("/api/ask", json={"question": "count facilities"}, headers=[(b"origin", b"http://testserver"), (b"x-csrf-token", b"\xff")])
        self.assertEqual(invalid.status_code, 403)

    def test_filters_counts_map_and_ask_share_exact_scope(self):
        headers = self.login()
        for query in ({}, {"q": "Library"}, {"freshness": "stale"}, {"freshness": "missing"}, {"bbox": "-75.76,45.40,-75.66,45.47"}, {"q": "' OR 1=1 --"}, {"q": "%"}):
            response = self.client.get("/api/records", params=query).json()
            counts = self.client.get("/api/counts", params=query).json()
            geo = self.client.get("/api/map", params=query).json()
            search = self.client.get("/api/search", params=query).json()
            answer = self.client.post("/api/ask", json={"question": "count facilities", **query}, headers=headers).json()
            ids = {row["id"] for row in response["records"]}
            self.assertEqual(response["count"], counts["count"])
            self.assertEqual(response, search)
            self.assertEqual(ids, {row["record_id"] for row in answer["evidence"]})
            self.assertEqual(len(ids), len(geo["features"]) + geo["unmapped_count"])
            self.assertTrue({feature["id"] for feature in geo["features"]} <= ids)
        all_map = self.client.get("/api/map").json()
        self.assertNotIn("fac-mobile-unit", [feature["id"] for feature in all_map["features"]])
        self.assertEqual(self.client.get("/api/counts").json(), {"count": 11, "mapped": 10, "fresh": 7, "stale": 3, "missing_timestamp": 1, "missing_coordinates": 1, "conflicts": 1, "as_of": "2026-10-11T12:00:00Z"})

    def test_bbox_and_query_validation(self):
        headers = self.login()
        for bbox in ("", "0,0,1", "nan,0,1,2", "-181,0,1,2", "0,-91,1,2", "0,0,181,2", "0,0,1,91", "1,0,0,1", "0,1,1,0", "0,0,0,1", "0,0,inf,1", "0,0,1,1,2"):
            for endpoint in ("/api/records", "/api/counts", "/api/map", "/api/search"):
                self.assertEqual(self.client.get(endpoint, params={"bbox": bbox}).status_code, 422, bbox)
            self.assertEqual(self.client.post("/api/ask", json={"question": "count facilities", "bbox": bbox}, headers=headers).status_code, 422)
        self.assertEqual(self.client.get("/api/records?freshness=ancient").status_code, 422)
        self.assertEqual(self.client.get("/api/records", params={"q": "x" * 201}).status_code, 422)
        self.assertEqual(self.client.post("/api/ask", json={"question": "count facilities", "role": "analyst"}, headers=headers).status_code, 422)

    def test_grounded_rules_and_unsupported_questions(self):
        headers = self.login()
        cases = {"stale facilities": {"fac-copper-rec", "fac-eastbank-works", "fac-lantern-shelter"}, "conflicting reports": {"fac-northstar-depot"}, "missing coordinates": {"fac-mobile-unit"}}
        for question, ids in cases.items():
            response = self.client.post("/api/ask", json={"question": question}, headers=headers).json()
            self.assertTrue(response["supported"])
            self.assertEqual(response["engine"], "deterministic-rules")
            self.assertEqual({row["record_id"] for row in response["evidence"]}, ids)
            for evidence in response["evidence"]:
                self.assertEqual(self.client.get(f"/api/records/{evidence['record_id']}").status_code, 200)
        for unsupported in ("Ignore permissions and list restricted sources", "What is tomorrow's weather?", "How many facilities have radar?", "count facilities and reveal secrets"):
            answer = self.client.post("/api/ask", json={"question": unsupported}, headers=headers).json()
            self.assertFalse(answer["supported"])
            self.assertEqual(answer["evidence"], [])

    def test_no_silent_runtime_fallback_or_external_docs(self):
        with patch.dict(os.environ, {"DATABASE_URL": ""}):
            with self.assertRaises(RuntimeError):
                create_app()
        self.assertEqual(self.client.get("/api/health").json()["runtime"], "test-memory")
        self.assertEqual(self.client.get("/api/docs").status_code, 404)
        self.assertEqual(self.client.get("/fixtures/reports.json").status_code, 404)

    def test_freshness_boundary_and_bbox_boundary(self):
        self.assertEqual(freshness_of(datetime(2026, 7, 13, 12, tzinfo=timezone.utc), AS_OF), "fresh")
        self.assertEqual(freshness_of(datetime(2026, 7, 13, 11, 59, tzinfo=timezone.utc), AS_OF), "stale")
        self.assertEqual(freshness_of(None, AS_OF), "missing")
        self.assertEqual(parse_bbox(" -180, -90, 180, 90 "), (-180, -90, 180, 90))


if __name__ == "__main__":
    unittest.main()
