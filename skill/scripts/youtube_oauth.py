#!/usr/bin/env python3
"""One-time OAuth loopback flow for the YouTube channel ops stack.

Why this exists: `yutu auth` requests only
  youtube, youtube.force-ssl, youtube.channel-memberships.creator
which leaves analytics dead (no yt-analytics scope in the token). This script runs the
same Desktop-app OAuth client through a loopback redirect and requests the full set,
including analytics, then writes `youtube.token.json` in the exact JSON shape yutu and
`youtube_analytics.py` both read.

Usage:
  python youtube_oauth.py                 # print URL, wait for consent, write token
  python youtube_oauth.py --port 8123
  python youtube_oauth.py --url-only      # print URL and exit (advanced)

After success: `youtu channel list --mine --output json` proves the token works for the
Data API, and `youtube_analytics.py` proves the analytics scope.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import sys
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

CLIENT = os.environ.get(
    "YUTU_CREDENTIAL", r"C:/Users/rest/.youtube-ops/client_secret.json")
TOKEN_OUT = os.environ.get(
    "YUTU_CACHE_TOKEN", r"C:/Users/rest/.youtube-ops/youtube.token.json")

SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/yt-analytics-monetary.readonly",
]

DONE_HTML = b"""<!doctype html><meta charset=utf-8>
<title>Authorised</title><body style="background:#0d1117;color:#e6edf3;
font:16px/1.6 -apple-system,Segoe UI,sans-serif;padding:12vh 8vw">
<h1 style="color:#ff4d2e">Authorised</h1>
<p>Token received. You can close this tab and return to Discord.</p></body>"""


def load_client() -> tuple[str, str]:
    if not os.path.exists(CLIENT):
        sys.exit(f"ERROR: client secret not found at {CLIENT}")
    node = json.load(open(CLIENT, encoding="utf-8")).get("installed") or {}
    if not node.get("client_id"):
        sys.exit("ERROR: client secret is not a Desktop-app 'installed' client")
    return node["client_id"], node["client_secret"]


class Handler(BaseHTTPRequestHandler):
    code: str | None = None
    error: str | None = None

    def do_GET(self):  # noqa: N802
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        Handler.code = (q.get("code") or [None])[0]
        Handler.error = (q.get("error") or [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(DONE_HTML if Handler.code else
                         f"<pre>error: {Handler.error}</pre>".encode())
        print(f"\n[oauth] callback received: "
              f"{'code' if Handler.code else 'ERROR ' + str(Handler.error)}", flush=True)

    def log_message(self, *a):
        pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8123)
    ap.add_argument("--url-only", action="store_true")
    args = ap.parse_args()

    cid, csec = load_client()
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    redirect = f"http://localhost:{args.port}"

    auth_url = "https://accounts.google.com/o/oauth2/auth?" + urllib.parse.urlencode({
        "client_id": cid,
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": secrets.token_urlsafe(16),
    })
    print("OPEN THIS URL AND APPROVE ALL FOUR PERMISSIONS:\n", flush=True)
    print(auth_url, flush=True)
    if args.url_only:
        return

    srv = HTTPServer(("127.0.0.1", args.port), Handler)
    srv.timeout = 600
    print(f"\n[oauth] waiting for the redirect on {redirect} (10 min max)", flush=True)
    deadline = time.time() + 600
    while Handler.code is None and Handler.error is None and time.time() < deadline:
        srv.handle_request()
    srv.server_close()

    if not Handler.code:
        sys.exit(f"ERROR: no authorization code ({Handler.error or 'timed out'})")

    body = urllib.parse.urlencode({
        "code": Handler.code, "client_id": cid, "client_secret": csec,
        "redirect_uri": redirect, "grant_type": "authorization_code",
        "code_verifier": verifier,
    }).encode()
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token", data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        tok = json.load(resp)

    token = {
        "access_token": tok["access_token"],
        "token_type": tok.get("token_type", "Bearer"),
        "refresh_token": tok.get("refresh_token", ""),
        "expiry": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                time.gmtime(time.time() + tok.get("expires_in", 0))),
        "scope": tok.get("scope", " ".join(SCOPES)),
    }
    if not token["refresh_token"]:
        sys.exit("ERROR: no refresh_token returned — re-run (prompt=consent should force it)")
    with open(TOKEN_OUT, "w", encoding="utf-8") as fh:
        json.dump(token, fh)
    print(f"\n[oauth] TOKEN WRITTEN -> {TOKEN_OUT}", flush=True)
    print("[oauth] granted scopes:", token["scope"], flush=True)


if __name__ == "__main__":
    main()
