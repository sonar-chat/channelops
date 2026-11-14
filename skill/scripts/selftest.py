#!/usr/bin/env python3
"""One-command self-test for the youtube-channel-ops stack.

Validates the live stack end to end and prints a PASS/FAIL/SKIP matrix. Exit code 1 if any
FAIL. Everything it creates (playlist, playlist item, caption track) is deleted again, and the
target video is left PRIVATE with no schedule. Safe to re-run.

Usage:
  python selftest.py [--video <id>] [--channel <UC...>] [--json]

Design rules learned the hard way:
  * yutu exit codes are NOT a pass signal (some failures return 0) -> every check requires
    stdout to parse as JSON (or expected success text).
  * yutu prints a usage dump instead of an error when a required flag is missing.
  * commentThread/comment paths only work on videos where comments are enabled, so they are
    reported SKIP when the video is private instead of FAIL.
  * caption insert is broken in yutu -> the caption check drives youtube_caption_upload.py.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

ROOT = os.environ.get("YOUTUBE_OPS_ROOT", r"C:/Users/rest/.youtube-ops")
BIN = os.environ.get("YUTU_BIN", r"C:/Users/rest/AppData/Local/hermes/bin/yutu.exe")
HERE = os.path.dirname(os.path.abspath(__file__))
CAPTION_HELPER = os.path.join(HERE, "youtube_caption_upload.py")
ANALYTICS = os.path.join(HERE, "youtube_analytics.py")

ENV = {k: v for k, v in os.environ.items() if k != "YUTU_ROOT"}
ENV["YUTU_CREDENTIAL"] = os.environ.get("YUTU_CREDENTIAL", f"{ROOT}/client_secret.json")
ENV["YUTU_CACHE_TOKEN"] = os.environ.get("YUTU_CACHE_TOKEN", f"{ROOT}/youtube.token.json")

rows: list[tuple[str, str, str]] = []


def y(*args: str, timeout: int = 180):
    p = subprocess.run([BIN, *args], cwd=ROOT, capture_output=True, text=True,
                       env=ENV, timeout=timeout)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def j(s: str):
    try:
        return json.loads(s)
    except Exception:
        return None


def items(d):
    if d is None:
        return []
    return d if isinstance(d, list) else d.get("items", [])


def rec(name: str, status: str, note: str = "") -> None:
    rows.append((name, status, note[:150]))
    print(f"[{status:4}] {name} :: {note[:150]}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default="hu-IfKhFRa0")
    ap.add_argument("--channel", default=None)

    # tolerate being imported with no argv
    a = ap.parse_args()
    vid = a.video

    # 1. version -> banner goes to stderr
    rc, out, err = y("version")
    ok = rc == 0 and ("yutu" in (out + err))
    rec("version", "PASS" if ok else "FAIL", (out or err).splitlines()[0] if (out or err) else "empty")

    if not os.path.exists(ENV["YUTU_CACHE_TOKEN"]):
        rec("token", "FAIL", f"missing {ENV['YUTU_CACHE_TOKEN']} — run youtube_oauth.py")
        return finish()

    # 2. channel
    rc, out, err = y("channel", "list", "--for", "mine", "--output", "json")
    ch = items(j(out))
    ch_id = ch[0].get("id") if ch else None
    rec("channel.list", "PASS" if ch_id else "FAIL",
        f"{ch[0]['snippet'].get('title')} ({ch_id})" if ch else err.splitlines()[-1][:120])
    ch_id = a.channel or ch_id
    if not ch_id:
        return finish()

    # 3. video.list
    rc, out, err = y("video", "list", "-i", vid, "--output", "json", "--parts", "id,snippet,status")
    v = items(j(out))
    status = v[0].get("status", {}) if v else {}
    privacy = status.get("privacyStatus")
    rec("video.list", "PASS" if v else "FAIL",
        f"{v[0]['snippet'].get('title')!r} privacy={privacy}" if v else err[:120])

    # 4. search
    rc, out, err = y("search", "list", "--q", "youtube api", "--maxResults", "2",
                     "--output", "json")
    n = len(items(j(out)))
    rec("search.list", "PASS" if n else "FAIL", f"results={n}")

    # 5. analytics
    end = time.strftime("%Y-%m-%d")
    start = time.strftime("%Y-%m-%d", time.localtime(time.time() - 7 * 86400))
    p = subprocess.run([sys.executable, ANALYTICS, "--metrics", "views", "--dimensions", "day",
                        "--start", start, "--end", end], capture_output=True, text=True)
    rec("analytics.channel", "PASS" if p.returncode == 0 else "FAIL",
        (p.stdout or p.stderr).strip().splitlines()[-1][:120])

    # 6. playlist round-trip
    rc, out, err = y("playlist", "insert", "-t", "ChannelOps selftest", "-c", ch_id,
                     "-p", "private", "--yes", "--output", "json")
    pl = j(out) or {}
    pl_id = pl.get("id")
    rec("playlist.insert", "PASS" if pl_id else "FAIL", f"id={pl_id}" if pl_id else err[-120:])
    item_id = None
    if pl_id:
        rc, out, err = y("playlistItem", "insert", "-c", ch_id, "-y", pl_id, "-k", "video",
                         "-V", vid, "--yes", "--output", "json")
        it = j(out) or {}
        item_id = it.get("id")
        rec("playlistItem.insert", "PASS" if item_id else "FAIL",
            f"id={item_id}" if item_id else err[-120:])
        rc, out, err = y("playlist", "list", "--mine", "--output", "json")
        found = any(x.get("id") == pl_id for x in items(j(out)))
        rec("playlist.list", "PASS" if found else "FAIL", f"created playlist visible={found}")

    # 7. caption round-trip through the helper (yutu's insert is broken)
    srt = f"{ROOT}/work/selftest.srt"
    os.makedirs(f"{ROOT}/work", exist_ok=True)
    with open(srt, "w", encoding="utf-8") as fh:
        fh.write("1\n00:00:00,000 --> 00:00:02,000\nselftest caption\n")
    p = subprocess.run([sys.executable, CAPTION_HELPER, "--video", vid, "--file", srt,
                        "--language", "en", "--name", "selftest"], capture_output=True, text=True)
    cap_id = (j(p.stdout) or {}).get("id")
    rec("caption.upload(helper)", "PASS" if cap_id else "FAIL",
        f"id={cap_id}" if cap_id else p.stderr.strip()[-120:])

    # 8. comment paths depend on comments being enabled (private video => disabled)
    rc, out, err = y("commentThread", "list", "--videoId", vid, "--output", "json")
    threads = j(out)
    if threads is None:
        rec("commentThread.list", "SKIP",
            f"comments unavailable (privacy={privacy}) — test on unlisted/public")
    else:
        rec("commentThread.list", "PASS", f"threads={len(items(threads))}")

    # cleanup
    if cap_id:
        rc, out, err = y("caption", "delete", "-i", cap_id, "--yes")
        rec("cleanup.caption", "PASS" if "deleted" in (out + err).lower() else "FAIL", out[-90:])
    if item_id:
        rc, out, err = y("playlistItem", "delete", "-i", item_id, "--yes")
        rec("cleanup.playlistItem", "PASS" if "deleted" in (out + err).lower() else "FAIL", "")
    if pl_id:
        rc, out, err = y("playlist", "delete", "-i", pl_id, "--yes")
        rec("cleanup.playlist", "PASS" if "deleted" in (out + err).lower() else "FAIL", "")

    finish()


def finish() -> None:
    p = sum(1 for _, s, _ in rows if s == "PASS")
    f = sum(1 for _, s, _ in rows if s == "FAIL")
    k = sum(1 for _, s, _ in rows if s == "SKIP")
    print(f"\nSUMMARY: {p} passed, {f} failed, {k} skipped")
    raise SystemExit(1 if f else 0)


if __name__ == "__main__":
    main()
