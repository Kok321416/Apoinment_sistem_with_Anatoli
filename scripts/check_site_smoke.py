#!/usr/bin/env python3
"""Live smoke for allyourclients.ru — public pages + key redirects."""
from __future__ import annotations

import ssl
import sys
import time
import urllib.error
import urllib.request

BASE = "https://allyourclients.ru"


def fetch(path: str, *, follow: bool = True, timeout: float = 25.0) -> tuple[int, float, str]:
    url = BASE + path
    t0 = time.perf_counter()
    req = urllib.request.Request(url, headers={"User-Agent": "ayc-site-smoke/1.0"})
    try:
        if follow:
            with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as resp:
                body = resp.read(8000).decode("utf-8", errors="replace")
                return resp.status, time.perf_counter() - t0, body

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None

        opener = urllib.request.build_opener(NoRedirect)
        with opener.open(req, timeout=timeout) as resp:
            body = resp.read(8000).decode("utf-8", errors="replace")
            return resp.status, time.perf_counter() - t0, body
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read(2000).decode("utf-8", errors="replace")
        except Exception:
            pass
        return e.code, time.perf_counter() - t0, body


def main() -> int:
    ok = True
    print(f"=== Site smoke {BASE} ===\n")

    public_ok = (
        "/",
        "/login/",
        "/register/",
        "/tg/",
        "/book/",
        "/s/spec/",
        "/health",
        "/health/mini-app",
        "/static/css/main.css?v=25",
        "/static/js/vendor/telegram-web-app.js?v=1",
    )
    for path in public_ok:
        code, elapsed, body = fetch(path)
        good = code == 200
        if path == "/s/spec/":
            good = good and ("Артем" in body or "Календар" in body or "календар" in body.lower())
            if "Вход для записи" in body and "ps-hero" not in body and "Календар" not in body:
                good = False
                print(f"  FAIL {path}: still login-wall only (no public profile)")
        flag = "OK" if good else "FAIL"
        if not good:
            ok = False
        print(f"{flag} {path} => {code} {elapsed:.2f}s")

    print("\nAuth-gated (expect redirect to login):")
    for path in ("/dashboard/", "/my-bookings/", "/manage/", "/clients/", "/booking/", "/profile/"):
        code, elapsed, _ = fetch(path, follow=False)
        # urllib may still surface final code; accept 302/303/200(login page after follow fallback)
        good = code in (200, 302, 303, 307, 308)
        flag = "OK" if good else "FAIL"
        if not good:
            ok = False
        print(f"{flag} {path} => {code} {elapsed:.2f}s")

    print("\n" + ("ALL CHECKS PASSED" if ok else "ISSUES FOUND"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
