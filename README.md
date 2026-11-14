# YouTube Channel Ops

CLI-driven operations on a YouTube channel you own: upload, schedule, edit metadata,
thumbnails, captions, playlists, comments, and read private analytics — driven by an AI
agent or by hand. No SaaS, no middleman API: your own Google OAuth client, your own token,
your own machine.

Built and verified against a live channel (v0.11.0 of [`yutu`](https://github.com/eat-pray-ai/yutu),
14 Nov 2026). The agent-facing procedure lives in [`skill/SKILL.md`](skill/SKILL.md).

## What's in here

```
skill/                          the Hermes skill: procedure + pitfalls + capability matrix
  SKILL.md
  references/
    yutu-setup-this-host.md     install layout, verified per-verb flags, quota table
    gcp-oauth-publication.md    the whole Google console gate, in order
    tool-candidate-vetting.md   how to prove a CLI/MCP candidate before adopting it
  scripts/
    selftest.py                 one-command stack verification (self-cleaning)
    youtube_oauth.py            full-scope OAuth incl. analytics (yutu's own auth omits it)
    youtube_analytics.py        Analytics API v2 reports (fills yutu's gap)
    youtube_caption_upload.py   working captions.insert (yutu's insert is broken)
docs/                           optional policy pages + logo for an OAuth consent screen
```

## Quick start

### 1. Engine

```bash
# standalone binary (recommended on Windows — the npm shim breaks under git-bash)
curl -L -o yutu.exe https://github.com/eat-pray-ai/yutu/releases/latest/download/yutu-windows-amd64.exe
yutu.exe version
```

### 2. Google Cloud (one time, ~5 min)

1. Create a project; enable **YouTube Data API v3** and **YouTube Analytics API**.
2. **Google Auth Platform → Branding**: app name, support email, developer contact.
3. **Data access**: add scopes
   `.../auth/youtube`, `.../auth/yt-analytics.readonly`, `.../auth/yt-analytics-monetary.readonly`.
4. **Audience**: add your account as a test user; **Publish app** for a long-lived refresh token
   (unpublished/Testing tokens die after 7 days).
5. **Clients → Create credentials → OAuth client ID → Desktop app** → download JSON as
   `client_secret.json`. Keep it out of git.

> App *verification* (the demo-video request) is optional — it only removes the "unverified app"
> warning for the consent screen. A single-user app works without it.

### 3. Token

```bash
python skill/scripts/youtube_oauth.py --port 8124
# open the printed URL, approve all four permissions, the token lands in youtube.token.json
```

`yutu auth` requests only youtube scopes — no analytics — which is why this script exists.

### 4. Prove it

```bash
python skill/scripts/selftest.py --video <videoId>
# 12 passed, 0 failed, 1 skipped  (comment check skips while the video is private)
```

## Quota arithmetic (Data API default 10,000 units/day)

| Call | Units |
|---|---|
| `videos.insert` (upload) | 1600 → **max 6 uploads/day** |
| `captions.insert` | 400 |
| `captions.update` | 450 |
| `videos.update` | 50 |
| `videos.list` / `commentThread.list` | 1 |
| `search.list` | 100 (separate bucket) |

## Known limitations (measured, not guessed)

- `yutu caption insert` always fails `400 invalidMetadata` → use `youtube_caption_upload.py`.
- `yutu comment insert` is **reply-only** (`--parentId` required); no top-level comments.
- Comments are disabled while a video is private, so comment calls 403 on a private test upload.
- yutu appends its own `yutu🐰` tag to every upload/update; it can't be stripped via the CLI.
- yutu sometimes exits **0** on failure — validate that stdout parses as JSON, not the exit code.
- File arguments must be **relative** to the yutu working directory (`path escapes from parent`).

## License

MIT for the scripts and skill text. `yutu` is Apache-2.0, © its authors. Not affiliated with
Google or YouTube.
