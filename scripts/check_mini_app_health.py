#!/usr/bin/env python3
"""Check prod Mini App prerequisites (DNS, HTTPS, static SDK). Run locally."""
from __future__ import annotations

import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode

DOMAIN = "allyourclients.ru"
BASE = f"https://{DOMAIN}"


def doh(name: str, rtype: str) -> dict:
    q = urlencode({"name": name, "type": rtype})
    req = urllib.request.Request(
        f"https://cloudflare-dns.com/dns-query?{q}",
        headers={"accept": "application/dns-json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def fetch(url: str, timeout: float = 20.0) -> tuple[int, float, int]:
    t0 = time.perf_counter()
    req = urllib.request.Request(url, headers={"User-Agent": "ayc-mini-app-check/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as resp:
            body = resp.read(512)
            elapsed = time.perf_counter() - t0
            return resp.status, elapsed, len(body)
    except urllib.error.HTTPError as e:
        elapsed = time.perf_counter() - t0
        return e.code, elapsed, 0


def main() -> int:
    print(f"=== Mini App diagnostics for {DOMAIN} ===\n")
    ok = True

    a = doh(DOMAIN, "A").get("Answer") or []
    aaaa = doh(DOMAIN, "AAAA").get("Answer") or []
    print("DNS @ A:", [x.get("data") for x in a] or "NONE")
    print("DNS @ AAAA:", [x.get("data") for x in aaaa] or "NONE (good)")
    if aaaa:
        ok = False
        print("  FAIL: AAAA still published - phones may hang on IPv6")

    for path in ("/tg/", "/static/js/vendor/telegram-web-app.js?v=1", "/health/mini-app"):
        code, elapsed, _ = fetch(BASE + path)
        flag = "OK" if code == 200 else "FAIL"
        if code != 200:
            ok = False
        print(f"HTTPS {path} => {code} in {elapsed:.2f}s [{flag}]")
        if path == "/tg/" and elapsed > 3.0:
            print("  WARN: /tg/ slow on first hit (Passenger cold start)")

    print("\nTelegram UA /tg/:")
    req = urllib.request.Request(
        BASE + "/tg/",
        headers={"User-Agent": "Mozilla/5.0 Telegram/10.0 MiniApp"},
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=20, context=ssl.create_default_context()) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    elapsed = time.perf_counter() - t0
    has_vendor = "/static/js/vendor/telegram-web-app.js" in html
    has_org = "telegram.org/js/telegram-web-app.js" in html
    print(f"  time={elapsed:.2f}s vendor_sdk={has_vendor} telegram_org={has_org}")
    if not has_vendor or has_org:
        ok = False
        print("  FAIL: expected self-hosted SDK only")

    print("\n" + ("ALL CHECKS PASSED" if ok else "ISSUES FOUND"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
