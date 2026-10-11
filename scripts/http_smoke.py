#!/usr/bin/env python3
"""Read-only local HTTP smoke plus disposable demo session creation/logout.

Run against Compose to exercise real PostGIS, or test-memory to validate routing.
The output names the runtime so the two cannot be confused.
"""
import argparse
import http.cookiejar
import json
import urllib.error
import urllib.parse
import urllib.request


class Client:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.csrf = ""

    def request(self, path: str, data=None, expected=200, csrf=True):
        headers = {"Origin": self.base}
        if self.csrf and csrf:
            headers["X-CSRF-Token"] = self.csrf
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base + path, data=json.dumps(data).encode() if data is not None else None, headers=headers)
        try:
            response = self.opener.open(request, timeout=15)
        except urllib.error.HTTPError as error:
            response = error
        body = response.read().decode()
        assert response.status == expected, f"{path}: expected {expected}, got {response.status}: {body}"
        return json.loads(body) if body else None

    def login(self, role):
        session = self.request("/api/login", {"role": role})
        self.csrf = session["csrf_token"]
        assert session["role"] == role


def no_canary(payload):
    assert "CANARY" not in json.dumps(payload).upper(), "restricted synthetic canary leaked into reader response"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    args = parser.parse_args()
    parsed = urllib.parse.urlparse(args.url)
    if parsed.scheme != "http" or parsed.hostname not in ("localhost", "127.0.0.1"):
        raise SystemExit("This smoke script only accepts a loopback HTTP demo URL.")
    client = Client(args.url)
    health = client.request("/api/health")
    assert health["synthetic"] is True
    assert client.request("/api/session") == {"authenticated": False}
    for path in ("/api/records", "/api/map", "/api/counts", "/api/search"):
        client.request(path, expected=401)
    client.login("reader")
    reader = client.request("/api/records")
    assert reader["count"] > 0
    no_canary(reader)
    counts = client.request("/api/counts")
    assert counts["count"] == reader["count"]
    no_canary(counts)
    for path in ("/api/map", "/api/search", "/api/records?role=analyst", "/api/search?q=CANARY"):
        no_canary(client.request(path))
    assert client.request("/api/search?q=CANARY")["count"] == 0
    client.request("/api/records?bbox=nan,0,1,2", expected=422)
    assert client.request("/api/records?bbox=0,0,1,1")["count"] == 0
    for item in reader["records"]:
        assert item["access"] == "public"
        detail = client.request("/api/records/" + item["id"])
        no_canary(detail)
        for source in detail["sources"]:
            assert source["url"].startswith("/api/"), "source link should remain local"
            no_canary(client.request(source["url"]))
    for question in ("count facilities", "stale facilities", "conflicting reports", "missing coordinates"):
        answer = client.request("/api/ask", {"question": question})
        no_canary(answer)
        assert answer["supported"] and answer["engine"] == "deterministic-rules"
    assert not client.request("/api/ask", {"question": "Predict next year's events"})["supported"]
    client.request("/api/ask", {"question": "count facilities"}, expected=403, csrf=False)
    client.login("analyst")
    analyst = client.request("/api/records")
    restricted = [item for item in analyst["records"] if item["access"] == "restricted"]
    assert restricted and analyst["count"] > reader["count"]
    assert "CANARY" in json.dumps(analyst).upper()
    for item in restricted:
        client.request("/api/records/" + item["id"])
    client.login("reader")
    for item in restricted:
        client.request("/api/records/" + item["id"], expected=404)
    no_canary(client.request("/api/records"))
    client.request("/api/logout", {}, expected=204)
    client.request("/api/records", expected=401)
    assert client.request("/api/session") == {"authenticated": False}
    print(f"PASS: HTTP auth/filter/evidence/canary smoke; runtime={health['runtime']}; reader={reader['count']}, analyst={analyst['count']}")


if __name__ == "__main__":
    main()
