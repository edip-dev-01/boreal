#!/usr/bin/env python3
"""Chromium UI smoke against a running local Boreal UI and API.

Optional QA dependency: pip install playwright; install Chromium separately.
This script does not upload anything or visit non-loopback URLs.
"""
import argparse
import json
from pathlib import Path
import shutil
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:5173")
    parser.add_argument("--screenshots", type=Path, default=Path("test-results/browser"))
    args = parser.parse_args()
    parsed = urlparse(args.url)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost"):
        raise SystemExit("Only loopback HTTP demo URLs are accepted.")
    args.screenshots.mkdir(parents=True, exist_ok=True)
    errors = []
    external = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=shutil.which("chromium") or shutil.which("google-chrome"), headless=True, args=["--no-sandbox", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        context = browser.new_context(viewport={"width": 1440, "height": 1050}, reduced_motion="reduce")
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        def inspect_request(request):
            url = urlparse(request.url)
            if url.scheme in ("http", "https", "ws", "wss") and url.hostname not in ("localhost", "127.0.0.1"):
                external.append(request.url)
        context.on("request", inspect_request)
        page.goto(args.url)
        expect(page.get_by_role("button", name="Explore as Reader")).to_be_enabled()
        page.screenshot(path=str(args.screenshots / "login-desktop.png"), full_page=True)
        page.get_by_role("button", name="Explore as Reader").click()
        expect(page.get_by_role("heading", name="Every record has a place.")).to_be_visible()
        expect(page.locator("tbody tr")).to_have_count(11)
        expect(page.get_by_role("button", name="Search this view")).to_be_enabled(timeout=20000)
        expect(page.get_by_label("Selected facility details").get_by_role("heading", name="Alder Library")).to_be_visible()
        assert "NIMBUS-RESTRICTED-CANARY-947" not in page.locator("body").inner_text()
        page.screenshot(path=str(args.screenshots / "reader-desktop.png"), full_page=True)
        page.get_by_role("tab", name="Evidence").click()
        expect(page.get_by_text("Field-level provenance links each reported value")).to_be_visible()
        source_link = page.get_by_role("link", name="Source reference").first
        expect(source_link).to_have_attribute("href", "/api/sources/src-civic")
        with page.expect_popup() as popup_info:
            source_link.click()
        popup = popup_info.value
        popup.wait_for_load_state()
        assert "synthetic" in popup.locator("body").inner_text()
        assert "CANARY" not in popup.locator("body").inner_text()
        popup.close()
        page.get_by_label("Search facilities").fill("no-such-demo-facility")
        expect(page.get_by_role("heading", name="No facilities match this view")).to_be_visible()
        page.get_by_role("button", name="Clear filters").click()
        expect(page.locator("tbody tr")).to_have_count(11)
        page.get_by_label("Freshness", exact=True).select_option("stale")
        expect(page.locator("tbody tr")).to_have_count(3)
        page.get_by_role("button", name="Stale records", exact=True).click()
        expect(page.locator(".answer")).to_contain_text("3 facilities")
        page.get_by_label("Freshness", exact=True).select_option("all")
        expect(page.locator("tbody tr")).to_have_count(11)
        page.get_by_role("button", name="Missing coordinates", exact=True).click()
        expect(page.locator(".answer")).to_contain_text("1 facilities")
        page.get_by_label("Question about visible facilities").fill("Predict the future")
        page.get_by_role("button", name="Ask question", exact=True).click()
        expect(page.locator(".answer")).to_contain_text("OUTSIDE DEMO QUESTION SCOPE")
        page.get_by_role("button", name="Search this view").click()
        expect(page.get_by_role("button", name="Map bounds")).to_be_visible()
        page.get_by_role("button", name="Reset", exact=True).click()
        expect(page.locator("tbody tr")).to_have_count(11)
        page.get_by_role("button", name="Switch role", exact=True).click()
        expect(page.get_by_role("button", name="Explore as Analyst")).to_be_enabled()
        assert "logout could not be confirmed" not in page.locator("body").inner_text()
        page.get_by_role("button", name="Explore as Analyst").click()
        expect(page.locator("tbody tr")).to_have_count(12)
        restricted_row = page.locator("tbody tr").filter(has_text="fac-canary-annex")
        restricted_row.get_by_role("button").click()
        expect(page.get_by_label("Selected facility details")).to_contain_text("NIMBUS-RESTRICTED-CANARY-947")
        page.get_by_role("button", name="Switch role", exact=True).click()
        page.get_by_role("button", name="Explore as Reader").click()
        expect(page.locator("tbody tr")).to_have_count(11)
        assert "NIMBUS-RESTRICTED-CANARY-947" not in page.locator("body").inner_text()
        # Recoverable data-fetch error must be visible and retryable.
        page.route("**/api/records?*", lambda route: route.fulfill(status=503, content_type="application/json", body=json.dumps({"detail": "Smoke-test datastore unavailable"})))
        page.get_by_label("Search facilities").fill("Alder")
        expect(page.get_by_role("alert")).to_contain_text("Smoke-test datastore unavailable")
        page.unroute("**/api/records?*")
        page.get_by_role("button", name="Try again", exact=True).click()
        expect(page.locator("tbody tr")).to_have_count(1)
        page.get_by_role("button", name="Reset", exact=True).click()
        expect(page.locator("tbody tr")).to_have_count(11)
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(args.screenshots / "reader-mobile.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), "Page overflows mobile viewport"
        # Expired sessions remove all scoped content instead of retaining stale details.
        context.clear_cookies()
        page.get_by_label("Search facilities").fill("Alder")
        expect(page.get_by_role("button", name="Explore as Reader")).to_be_visible()
        assert not page.get_by_label("Selected facility details").count()
        assert not errors, f"Browser exceptions: {errors}"
        assert not external, f"External runtime requests: {external}"
        browser.close()
    print("PASS: Chromium desktop/mobile login, map, table, filters, evidence/source links, QA, role switching, retry, expiry; zero page exceptions; zero external runtime requests.")


if __name__ == "__main__":
    main()
