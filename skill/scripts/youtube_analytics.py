#!/usr/bin/env python3
"""YouTube Analytics API v2 reports using yutu's own OAuth token.

Fills the one gap in yutu (no analytics command) without a second tool, a second
login, or a second dependency: reuses `youtube.token.json` written by `yutu auth`
and refreshes it with `client_secret.json`.

Usage:
  python youtube_analytics.py --metrics views,estimatedMinutesWatched \
      --dimensions day --start 2026-11-01 --end 2026-11-14
  python youtube_analytics.py --metrics views,estimatedMinutesWatched,averageViewDuration \
      --dimensions video --sort -views --max 10 --start 2026-10-01 --end 2026-11-14
  python youtube_analytics.py --metrics estimatedRevenue,estimatedAdRevenue \
      --dimensions day --start 2026-11-01 --end 2026-11-14   # monetary scope
  python youtube_analytics.py --raw --metrics views --dimensions day --start ... --end ...

Exit codes: 0 ok, 2 no credential/token, 3 refresh rejected (re-consent needed),
4 API error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

TOKEN_PATH = os.environ.get(
    "YUTU_CACHE_TOKEN", r"C:/Users/rest/.youtube-ops/youtube.token.json")
CRED_PATH = os.environ.get(
    "YUTU_CREDENTIAL", r"C:/Users/rest/.youtube-ops/client_secret.json")
REPORTS = "https://youtubeanalytics.googleapis.com/v2/reports"
TOKEN_URI = "https://oauth2.googleapis.com/token"


def die(code: int, msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(code)


def load(path: str, what: str) -> dict:
    if not os.path.exists(path):
        die(2, f"{what} not found at {path}")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        hint = ""
        if what == "client_secret":
            hint = (" — the file must be the downloaded OAuth *Desktop app* JSON "
                    "(top-level key 'installed').")
        die(2, f"{what} at {path} is not JSON: {exc}{hint}")


def client_pair(secret: dict) -> tuple[str, str]:
    node = secret.get("installed") or secret.get("web")
    if not node:
        die(2, "client_secret has neither 'installed' nor 'web' key — recreate it "
               "as an OAuth client of type *Desktop app*.")
    try:
        return node["client_id"], node["client_secret"]
    except KeyError as exc:
        die(2, f"client_secret missing field {exc}")


def refresh(token: dict, cid: str, csec: str) -> str:
    rt = token.get("refresh_token")
    if not rt:
        die(3, "token has no refresh_token — run `youtu auth` again and grant "
               "offline access.")
    body = urllib.parse.urlencode({
        "client_id": cid, "client_secret": csec,
        "refresh_token": rt, "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request(
        token.get("token_uri") or TOKEN_URI, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        if "invalid_grant" in detail:
            die(3, "refresh rejected (invalid_grant): the consent expired or was "
                   "revoked. Testing-mode apps expire in 7 days — publish the "
                   "consent screen, then run `youtu auth` again.\n" + detail)
        die(3, f"refresh failed HTTP {exc.code}: {detail}")
    token.update(payload)
    token["expiry"] = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + payload.get("expires_in", 0)))
    try:
        with open(TOKEN_PATH, "w", encoding="utf-8") as fh:
            json.dump(token, fh)
    except OSError:
        pass  # non-fatal: refreshed token still works for this run
    return payload["access_token"]


def access_token() -> str:
    token = load(TOKEN_PATH, "token (youtube.token.json)")
    cid, csec = client_pair(load(CRED_PATH, "client_secret"))
    expiry = token.get("expiry") or ""
    fresh = False
    if expiry:
        try:
            fresh = time.mktime(time.strptime(expiry, "%Y-%m-%dT%H:%M:%SZ")) - 120 > time.time()
        except ValueError:
            fresh = False
    if token.get("access_token") and fresh:
        return token["access_token"]
    return refresh(token, cid, csec)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--metrics", required=True,
                    help="comma list, e.g. views,estimatedMinutesWatched,averageViewDuration")
    ap.add_argument("--dimensions", default="day")
    ap.add_argument("--start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD")
    ap.add_argument("--ids", default="channel==MINE")
    ap.add_argument("--filters", default=None)
    ap.add_argument("--sort", default=None)
    ap.add_argument("--max", dest="max_results", type=int, default=None)
    ap.add_argument("--raw", action="store_true", help="dumb full JSON response")
    args = ap.parse_args()

    params = {
        "ids": args.ids, "startDate": args.start, "endDate": args.end,
        "metrics": args.metrics, "dimensions": args.dimensions,
    }
    if args.filters:
        params["filters"] = args.filters
    if args.sort:
        params["sort"] = args.sort
    if args.max_results:
        params["maxResults"] = str(args.max_results)

    url = f"{REPORTS}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {access_token()}",
                      "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:600]
        if exc.code == 401:
            die(3, "401 from Analytics API — token rejected. Re-run `youtu auth`; "
                   "the granted scopes must include yt-analytics.readonly.\n" + detail)
        if "forbidden" in detail.lower() or exc.code == 403:
            die(4, "403 from Analytics API — scope missing or channel has no data "
                   "for this range.\n" + detail)
        die(4, f"Analytics API HTTP {exc.code}: {detail}")

    if args.raw:
        print(json.dumps(data, indent=2))
        return

    headers = [c["name"] for c in data.get("columnHeaders", [])]
    rows = data.get("rows") or []
    if not rows:
        print(f"no rows for {args.start}..{args.end} (metrics={args.metrics})")
        return
    widths = [max(len(h), *(len(str(r[i])) for r in rows)) for i, h in enumerate(headers)]
    print("  ".join(h.ljust(w) for h, w in zip(headers, widths)))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print("  ".join(str(v).ljust(w) for v, w in zip(row, widths)))
    print(f"\n{len(rows)} row(s) | ids={args.ids} | {args.start}..{args.end}")


if __name__ == "__main__":
    main()
