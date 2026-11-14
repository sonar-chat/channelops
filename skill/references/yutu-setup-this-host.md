# yutu setup on this host — verified 2026-11-14

## Installed layout (this PC)

| What | Path |
|---|---|
| Binary (standalone, no node) | `C:/Users/rest/AppData/Local/hermes/bin/yutu.exe` — v0.11.0 windows/amd64, sha256 `6e1029f8…` |
| Convenience wrapper (pins paths, keeps secrets out of argv) | `C:/Users/rest/AppData/Local/hermes/bin/youtu` |
| OAuth client secret (**operator-supplied**) | `C:/Users/rest/.youtube-ops/client_secret.json` |
| Cached OAuth token (created by `youtu auth`) | `C:/Users/rest/.youtube-ops/youtube.token.json` |
| Working root for uploads/media | `C:/Users/rest/.youtube-ops/work` |

`youtu` is on PATH and exports `YUTU_CREDENTIAL`, `YUTU_CACHE_TOKEN`, `YUTU_ROOT`
before exec'ing the binary, so every command works from any CWD with no flags.

Do **not** `npm i -g @eat-pray-ai/yutu` on this host: the git-bash shim resolves
`%~dp0` against the wrong tree and dies with `MODULE_NOT_FOUND`. The release
binary above replaces it (npm package was uninstalled).

## GCP side — the only human steps (one time, ~6 clicks)

1. https://console.cloud.google.com → new project (any name).
2. **APIs & Services → Library** → enable:
   - `YouTube Data API v3` (required)
   - `YouTube Analytics API` (for views/watch time/retention)
   - optional: `YouTube Reporting API` (bulk daily reports)
3. **APIs & Services → OAuth consent screen** → External → fill app name +
   support email → add **your own Google account as a Test user**.
   - Test-user mode works immediately but **refresh tokens expire in 7 days**.
   - To make it permanent: click **Publish app**. Personal use with only your own
     account is not verified by Google; you will see "unverified app" once and
     click *Advanced → Go to app*.
4. On the consent screen **Scopes** step add:
   - `https://www.googleapis.com/auth/youtube` (write/upload/manage)
   - `https://www.googleapis.com/auth/yt-analytics.readonly` (analytics)
   - optional `…/auth/yt-analytics-monetary.readonly` (revenue)
   Add the analytics scope **now** — adding a scope later forces a full re-consent.
5. **Credentials → Create credentials → OAuth client ID → Desktop app** →
   *Download JSON* → save as `C:/Users/rest/.youtube-ops/client_secret.json`.

Shape check (top-level key must be `installed`, not `web`):

```json
{"installed":{"client_id":"…apps.googleusercontent.com","client_secret":"…",
 "redirect_uris":["http://localhost"]}}
```

## Auth

```bash
youtu auth          # opens the browser at localhost redirect; grant, token is written
youtu channel list --mine --output json   # proof: prints your channel id + title
```

`yutu auth` has no `--no-browser` / device-code flag (verified: `auth --help`
exposes only `-c`/`-t`), so the consent needs a desktop session on this machine.

## Verified command surface (0.11.0)

Upload — `video insert`:
`-f/--file  -t/--title  -d/--description  -g/--categoryId  -p/--privacy
-U/--publishAt  -u/--thumbnail  -y/--playlistId  -a/--tags  -l/--language
-L/--license  -K/--forKids  -N/--notifySubscribers  -M/--containsSyntheticMedia
-d/--recordingDate  -o/--output json|yaml|silent  --yes`

Edit — `video update`: `-i/--ids` + any of title/description/tags/categoryId/
privacy/`--publishAt`/thumbnail/playlistId, `--yes`.

Comments — `commentThread list`: `-v/--videoId`, `-a/--allThreadsRelatedToChannelId`,
`-m/--moderationStatus published|heldForReview|likelySpam|rejected`, `-n/--maxResults`,
`-s/--searchTerms`, `-o json|yaml|table`.
`comment insert`: `-v/--videoId`, `-t/--textOriginal`, `-P/--parentId` (reply), `--yes`.

Playlists — `playlist insert`: `-t -d -p -a --yes`; `playlistItem insert`:
`-y/--playlistId`, `-k/--kind video|channel|playlist`, `-V/-C/-Y` matching id, `--yes`.

Captions — `caption insert`: `-v/--videoId`, `-f/--file`, `-l/--language`,
`-n/--name`, `-t/--trackKind standard|ASR|forced`, `--yes`.

Thumbnails — `thumbnail set`: `-v/--videoId`, `-f/--file`, `--yes`.

Search — `search list --q --maxResults --order --publishedAfter --channelId --for mine`.

## Runtime pitfalls (measured, not guessed)

- **Missing credential error is misleading**: a nonexistent path is parsed as
  base64 and fails with `illegal base64 data at input byte 6`. Same for the token
  (`illegal base64 data at input byte 7`). Treat those as "file missing".
- **Exit codes are trustworthy** (real exit `1` on auth failure) — unlike some
  Go CLIs that log ERROR and return 0. Still grep for `level=ERROR` in stderr
  when a command's JSON output is empty.
- **Paths are relative to `YUTU_ROOT`**, not CWD, once the wrapper sets it.
- `--output table` is the default for read commands and is *not* parseable JSON;
  always pass `--output json` when the result is consumed by code.

## Quota (Data API default 10,000 units/day)

| Call | Units | Practical |
|---|---|---|
| `videos.insert` (upload) | 1600 | **max 6 uploads/day**, nothing else that day |
| `captions.insert` | 400 | |
| `captions.update` | 450 | |
| `captions.list` | 50 | |
| `videos.update` | 50 | prefer over re-upload |
| `videos.list` / `commentThread.list` | 1 | use ids, don't search |
| `search.list` | 100 | separate bucket |

Upload of >6/day needs a quota increase request in GCP (free, form).
