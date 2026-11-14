#!/usr/bin/env python3
"""Upload a caption track to a YouTube video (fill for yutu's broken caption.insert).

Measured 2026-11-14: `yutu caption insert` always fails with
  googleapi: Error 400 ... invalidMetadata
for the same video/language/name/file that the API accepts, so this script talks to
`captions.insert` directly with a correct multipart/related body. It reuses
`youtube.token.json` + `client_secret.json` (refreshing the access token when stale).

Usage:
  python youtube_caption_upload.py --video hu-IfKhFRa0 --file work/test.srt \
      --language en --name English [--draft]

Exit codes: 0 ok, 2 missing credential/token, 3 refresh/401, 4 API error.
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
import uuid

TOKEN_PATH = os.environ.get(
    "YUTU_CACHE_TOKEN", r"C:/Users/rest/.youtube-ops/youtube.token.json")
CRED_PATH = os.environ.get(
    "YUTU_CREDENTIAL", r"C:/Users/rest/.youtube-ops/client_secret.json")
URL = "https://www.googleapis.com/upload/youtube/v3/captions?part=snippet&uploadType=multipart"


def die(code: int, msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(code)


def access_token() -> str:
    if not (os.path.exists(TOKEN_PATH) and os.path.exists(CRED_PATH)):
        die(2, f"need {TOKEN_PATH} and {CRED_PATH} — run youtube_oauth.py first")
    tok = json.load(open(TOKEN_PATH, encoding="utf-8"))
    cred = json.load(open(CRED_PATH, encoding="utf-8"))
    node = cred.get("installed") or cred.get("web") or {}
    body = urllib.parse.urlencode({
        "client_id": node.get("client_id"), "client_secret": node.get("client_secret"),
        "refresh_token": tok.get("refresh_token"), "grant_type": "refresh_token"}).encode()
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token", data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            fresh = json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        die(3, f"token refresh failed ({exc.code}): {detail}")
    tok.update(fresh)
    try:
        json.dump(tok, open(TOKEN_PATH, "w", encoding="utf-8"))
    except OSError:
        pass
    return tok["access_token"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--file", required=True, help="path to .srt/.vtt (relative to cwd)")
    ap.add_argument("--language", required=True, help="BCP-47, e.g. en or ur")
    ap.add_argument("--name", default="", help="track name shown in Studio")
    ap.add_argument("--draft", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(a.file):
        die(2, f"caption file not found: {a.file}")
    meta = {"snippet": {"videoId": a.video, "language": a.language,
                        "name": a.name or a.language, "isDraft": bool(a.draft)}}
    boundary = "----cap" + uuid.uuid4().hex
    data = open(a.file, "rb").read()
    payload = b"".join([
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode(),
        json.dumps(meta).encode(), b"\r\n",
        f"--{boundary}\r\nContent-Type: application/octet-stream\r\n\r\n".encode(),
        data, b"\r\n",
        f"--{boundary}--\r\n".encode()])

    req = urllib.request.Request(URL, data=payload, headers={
        "Authorization": f"Bearer {access_token()}",
        "Content-Type": f"multipart/related; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            out = json.load(resp)
    except urllib.error.HTTPError as exc:
        die(4, f"captions.insert HTTP {exc.code}: "
               f"{exc.read().decode('utf-8', 'replace')[:500]}")
    print(json.dumps({"id": out.get("id"),
                      "snippet": out.get("snippet", {})}, indent=2))


if __name__ == "__main__":
    main()
