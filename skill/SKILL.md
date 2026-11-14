---
name: youtube-channel-ops
description: "Use for YouTube channel ops: upload, schedule, comments."
version: 1.0.0
author: rest
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [youtube, channel, upload, scheduling, oauth, analytics, yutu]
    category: productivity
    related_skills: [agent-reach]
---

# YouTube Channel Ops

Write-plane work on a channel the operator owns: upload, publish/schedule, metadata edits,
thumbnails, captions, playlists, comment moderation, live/branding, plus the private
analytics read. **Not** transcript/public-metadata research — that is the read plane and it
lives in the `agent-reach` skill (its video reference covers YouTube, Bilibili, podcasts).

## When to Use

- "upload this video", "schedule it for Thursday", "fix the title/description/tags",
  "swap the thumbnail", "answer/moderate comments", "how did the last video do".
- Any request that needs OAuth on the operator's own channel.

## Step 0 — name the plane before shortlisting tools

Read plane (transcripts, search, channel listings, public stats) needs **no credentials**:
`yt-dlp` covers it. Write plane needs **OAuth + a GCP project**. These are different tool
classes and no single tool in this space does both well — say which plane the request is in
before comparing repos, or you will hand back a transcript stack for an upload job.

## Backbone: `yutu` (eat-pray-ai/yutu)

One Go binary that mirrors the **whole YouTube Data API v3** as a CLI, plus an MCP server and
a skill (`yutu mcp setup -a claude,codex`, `npx skills add eat-pray-ai/yutu --skill youtube`).
It is the only actively maintained tool in this class that covers upload, scheduling,
comments, captions, thumbnails, playlists, live and branding in one surface.

```bash
youtu version                   # installed here: wrapper on PATH -> yutu.exe v0.11.0
```

**This host is already configured** (see `references/yutu-setup-this-host.md`):
release binary at `hermes/bin/yutu.exe`, bash wrapper `youtu` on PATH that pins
`YUTU_CREDENTIAL` / `YUTU_CACHE_TOKEN` to `C:/Users/rest/.youtube-ops/` and `cd`s there —
it deliberately leaves `YUTU_ROOT` unset, because that variable breaks credential resolution.
Never `npm i -g` here — the git-bash shim resolves against the wrong tree (`MODULE_NOT_FOUND`).

```bash
youtu channel list --for mine --output json    # proof of life: id, title, handle
```

Flag is `--for mine`, not `--mine` (common miss). List commands emit a **bare JSON array**, not
`{"items": [...]}` — parse both shapes or the code dies on `.get('items')`. Statistics are
absent unless `--parts` includes them (`--parts id,snippet,statistics`).

Command families: `video comment commentThread playlist playlistItem caption thumbnail
channel channelBanner channelSection watermark liveBroadcast liveChat* subscription search
activity member superChatEvent thirdPartyLink i18n*`.

Verified upload invocation (flags re-checked against 0.11.0 on this host):

```bash
youtu video insert --file out.mp4 --title 'T' --description d.txt --categoryId 22 \
  --privacy private --publishAt 2026-12-01T15:00:00Z --thumbnail cover.jpg \
  --playlistId PL... --tags 'a,b' --output json --yes
```

- `--publishAt` schedules; `--yes` is what makes it non-interactive — without it an
  unattended run blocks on a prompt.
- `--output json|yaml|silent` for machine-readable results; parse the returned video id.
- Credentials: `YUTU_CREDENTIAL` / `YUTU_CACHE_TOKEN` accept **path, base64 or JSON** — pass a
  path, never inline secrets in argv where shell history keeps them.

## Auth: use `scripts/youtube_oauth.py`, not `yutu auth`

`yutu auth` requests only `youtube`, `youtube.force-ssl`, `youtube.channel-memberships.creator`
(verified by decoding the auth URL it prints). **No analytics scope** — a token minted by yutu
can never read Analytics. Use the loopback flow instead; it requests all four scopes and writes
`youtube.token.json` in the shape yutu and `youtube_analytics.py` both read:

```bash
O="C:/Users/rest/AppData/Local/hermes/skills/productivity/youtube-channel-ops/scripts/youtube_oauth.py"
python "$O" --port 8124        # prints a URL; operator opens it, approves, token is written
```

Run it as a background process (`terminal(background=true)`) — it blocks on a local HTTP
listener until the redirect arrives. Google accepts any loopback port for a Desktop-app client,
so `--port` is free to choose. Consent needs a desktop browser on the same machine; there is no
device-code path in this stack.

## Quota arithmetic — plan the batch, don't discover the wall

Default Data API budget is 10,000 units/day, and `videos.insert` costs **1600**: that is
**6 uploads/day** and nothing else that day. `captions.insert` 400, `captions.update` 450,
`captions.list` 50, `videos.update` 50, `videos.list` 1. `search.list` is 100 but sits in its
own bucket. Prefer one `videos.update` over a re-upload, and pull ids with `videos.list`
(1 unit) instead of searching for them.

## Analytics is yutu's gap — fill it with Analytics API v2, same token

There is no analytics command in yutu. Add the scope `yt-analytics.readonly` at consent time
and query the same token directly:

```
GET https://youtubeanalytics.googleapis.com/v2/reports
    ?ids=channel==MINE&startDate=YYYY-MM-DD&endDate=YYYY-MM-DD
    &metrics=views,estimatedMinutesWatched,averageViewDuration
    &dimensions=day&sort=day
Authorization: Bearer <access_token from youtube.token.json>
```

Retention/revenue need the same endpoint with `dimensions=video` and the matching metrics.
**Use `scripts/youtube_analytics.py`** — it reuses yutu's token, refreshes it, and prints a
table (no google-api-python-client needed):

```bash
A="C:/Users/rest/AppData/Local/hermes/skills/productivity/youtube-channel-ops/scripts/youtube_analytics.py"
python "$A" --metrics views,estimatedMinutesWatched --dimensions day --start 2026-11-01 --end 2026-11-14
python "$A" --metrics views,averageViewDuration --dimensions video --sort -views --max 10 --start 2026-10-01 --end 2026-11-14
python "$A" --metrics estimatedRevenue,estimatedAdRevenue --dimensions day --start ... --end ...   # monetary scope
```

Exit codes: 2 = credential/token missing, 3 = refresh rejected (re-consent), 4 = API error.
`invalid_grant` almost always means a Testing-mode consent (7-day token) or a revoked scope.

## Pitfalls

- **Exit codes lie on some failures.** `commentThread list` on a private video prints
  `Error: failed to get comment thread` and still exits **0**. `version` succeeds with rc 0 but
  writes only to stderr. Always validate that stdout parses as JSON before trusting a result —
  rc is not a pass/fail signal.
- **Several subcommands demand flags their `--help` marks optional**: `playlist insert` and
  `playlistItem insert` need `-c/--channelId`; `playlist list` needs an explicit `--mine`;
  `comment insert` needs `-P/--parentId` (it can only *reply*, never start a thread). Missing
  ones surface as a full usage dump, not a clean error.
- **Comments are disabled while a video is private**, so `commentThread list`/`comment insert`
  return 403-derived errors on a private test upload. Test the comment path on an unlisted or
  public video, never conclude "auth broken" from it.
- **`caption insert` is broken in yutu** (`Error 400 invalidMetadata` for any language/name
  combination the API accepts). Use `scripts/youtube_caption_upload.py`, which POSTs the correct
  multipart/related body to `captions.insert`.

- **File paths must be relative to the yutu root.** `videos.insert --file C:/abs/path.mp4` dies
  with `openat …: path escapes from parent` — yutu sandboxes reads to its working directory. Run
  from the ops dir and pass `work/clip.mp4`.
- **`--ids` is only on the `list` commands.** `video update` takes `-i/--id` (singular);
  `--ids` there fails with `unknown flag: --ids`, which the CLI prints *after* the whole flag
  table, so the real error is easy to miss.
- **yutu appends its own `yutu🐰` tag** to every `video insert` *and* `video update`, even when
  you pass `--tags` without it. It cannot be stripped through yutu — remove it in Studio or with
  a direct `videos.update`. Plan for it on any real upload (it is a visible public tag).

- **Never compare tools before naming the plane (Step 0).** Read-plane and write-plane repos
  rank completely differently; the mistake is expensive and looks like thorough research.
- **A "YouTube skills" repo that asks the agent for an email + OTP + `sk_` key is a paid API
  reseller, not a tool.** Those wrappers are read-only, bill per call and route queries through
  a third party. Reject them for any job a local CLI covers.
- **GUI-gated MCP servers do not automate.** A desktop app that requires a human to click Allow
  per client, or that only answers on `127.0.0.1:<port>` while its window is open, cannot run
  from cron or a detached job.
- **Consent screen in "Testing" mode expires refresh tokens in 7 days.** Publish the app for a
  long-lived token, or the channel breaks upstream without warning.
- **First real upload: private + `--yes`, then confirm with `videos.list`, then flip
  visibility.** Publishing is a write on a live property — get operator approval before the
  first public/scheduled flip, and never retry an upload blindly on a 5xx (duplicates cost
  1600 units each).
- **Windows/git-bash: never install yutu with npm here** — the shim resolves `%~dp0` against
  the wrong tree and dies with `MODULE_NOT_FOUND`. Use the release `.exe` + the `youtu`
  wrapper (both already installed).
- **`YUTU_ROOT` breaks credential resolution.** Measured on 0.11.0: with `YUTU_ROOT` exported,
yutu joins it onto the credential/token value and an absolute path dies with
`failed to parse client secret: illegal base64 data at input byte 1`. Leave `YUTU_ROOT` unset
and `cd` into the ops directory instead (the `youtu` wrapper does exactly this).
- **A missing/renamed credential file produces a misleading error**: a nonexistent path is
  parsed as base64 and fails with `illegal base64 data at input byte 6` (token: `byte 7`).
  Read those as "file not there", not as a corrupt secret.
- **Read commands default to `--output table`**, which is not machine-parseable. Always pass
  `--output json` when code consumes the result. Exit codes are honest (`1` on auth failure).
- **Analytics on a dormant channel returns `no rows`, not an error.** Verify the pipeline with
  a lifetime range (`--start 2026-01-01 --end today`, no `--dimensions`) — a single row of
  zeros proves scope + endpoint are fine.
- **Add the Analytics scope at consent time, not later.** Adding a scope forces a full
  re-consent; a channel that half-works is worse than one that asks once.
- **Publishing the GCP app is a prerequisite for a durable token, and it has its own gate.**
  Sensitive scopes will not publish until the Branding *App domain* block has live URLs on a
  domain you own, and a failed attempt starts a ~24h retry cooldown. See
  `references/gcp-oauth-publication.md` before touching the console.

## Measured capability matrix (0.11.0, live channel, 2026-11-14)

| Verb | Result | Notes |
|---|---|---|
| `version` | works | prints its banner to **stderr**, stdout empty — `rc` 0 |
| `channel list --for mine` | works | returns a **list** in `--output json` |
| `video list -i <id>` | works | honors `--parts id,snippet,status` |
| `video insert` | works | 2.4 s for a 991 KB clip; response = **single object** |
| `video update -i` | works | partial updates OK; `-U ""` **clears** a scheduled `publishAt` |
| `thumbnail set -v -f` | works | response is a thumbnail-set object with `items[]` |
| `search list --q` | works | 100 quota units |
| `playlist insert` | works | **requires `-c/--channelId`** |
| `playlistItem insert` | works | **requires `-c/--channelId`** too |
| `playlist list` | works | **requires an explicit `--mine`** or `--channelId`/`--ids` |
| `playlistItem delete`, `playlist delete` | works | `-i <id> --yes` |
| `caption list`, `caption delete` | works | sees tracks created by the API directly |
| `caption insert` | **BROKEN** | always `googleapi: Error 400 … invalidMetadata`; same payload succeeds through the API → use `scripts/youtube_caption_upload.py` |
| `commentThread list` | **blocked on private video** | `Error: failed to get comment thread` — comments are disabled while the video is private |
| `comment insert` | **reply-only** | `required flag(s) "parentId"` — no top-level comments; and the 403 on a private video (`insufficient permissions`) is YouTube, not auth |
| analytics (`youtube_analytics.py`) | works | channel + per-video; 0 rows on a channel with no views |

## Verification — measured on this channel (2026-11-14)

**One command re-proves the whole stack:** `python scripts/selftest.py` — 13 checks, creates and
removes its own playlist/item/caption, leaves the video private, exits non-zero on any FAIL.
Last run: **12 passed, 0 failed, 1 skipped** (comment check skips while the video is private).

Write path proven end to end on `Authentic Novels` (`UCE7rkgYdRr51a2Rng115oYw`) with a generated
5 s clip (ffmpeg `testsrc2` + `sine`, h264/aac, 991 KB):

```bash
cd C:/Users/rest/.youtube-ops
youtu video insert --file work/clip.mp4 --title 'T' --description 'D' \
  --categoryId 22 --privacy private --tags 'test' \
  --notifySubscribers=false --containsSyntheticMedia --output json --yes
# -> {"id":"hu-IfKhFRa0","status":{"privacyStatus":"private","uploadStatus":"uploaded"}}  (2.4 s)
youtu video list -i <id> --output json --parts id,snippet,status    # confirms privacy + title
```

`--output json` returns a **single object** for `insert`/`update` (not an array), and a **list**
for `channel list` / `video list` with `--output json`. Parse both shapes.

Checks that still matter for a new channel: `video insert --help` still shows
`--publishAt`/`--yes`; analytics numbers are cross-checked against Studio for one day before
being reported.

## Repo

The working copy lives at `C:/Users/rest/youtube-channel-ops` and pushes to
`git@github.com:sonar-chat/channelops.git` (branch `main`, SSH key
`C:/Users/rest/.ssh/github_ops`). Publish flow: rebase onto `origin/main` first (the remote also
carries the site's policy pages), then push. Never commit `client_secret.json` or
`youtube.token.json` — `.gitignore` covers both; `git grep --cached -E "GOCSPX-|ya29\."` before
every push.

## Support files

- `references/yutu-setup-this-host.md` — installed paths, ABI of the wrapper, the one-time GCP
  walkthrough, verified flag sets per verb, quota table, measured runtime pitfalls.
- `references/gcp-oauth-publication.md` — the console gate sequence for publishing an OAuth
  app (scopes → live policy pages → domain verification → Branding/App domain → Publish), the
  authorised-domain rules, the SPA catch-all trap, and the retry cooldown.
- `references/tool-candidate-vetting.md` — how to shortlist and prove a CLI/MCP candidate from
  GitHub before recommending it (measured evidence, red flags, verified-by-running rule).
- `scripts/selftest.py` — one-command stack verification (13 checks, self-cleaning, non-zero
exit on failure). Run it first whenever a session picks this skill up.
- `scripts/youtube_caption_upload.py` — working caption upload (yutu's `caption insert` is
  broken); reuses the same token.
- `scripts/youtube_oauth.py` — full-scope OAuth (incl. analytics) via loopback redirect; writes
  `youtube.token.json`. Use this instead of `yutu auth`.
- `scripts/youtube_analytics.py` — Analytics API v2 reports via yutu's own token (refreshes it,
  prints a table, exits 2/3/4 with actionable messages).
