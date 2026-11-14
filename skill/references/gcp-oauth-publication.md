# Publishing a GCP OAuth app so the token survives

Getting a consent to work is half the job. Until the app is published, refresh tokens die in
7 days and every consumer of the token breaks without warning. This is the gate sequence,
verified against the current Google Cloud console (the "OAuth consent screen" page is now the
**Google Auth Platform**: Overview · Branding · Audience · Clients · Data access).

## 1. Scopes — declare before the first consent

`Data access` → **Add or remove scopes**. Two entry points: filter the catalogue, or use
**Manually add scopes** at the bottom of the panel and paste the full URL (needed when the
filter won't surface a scope). Tick the row, **Update**, then **Save**.

Adding a scope after a token exists forces a full re-consent, so decide the scope set once.
For a read/write YouTube app that means `youtube`, `youtube.force-ssl`,
`yt-analytics.readonly`, `yt-analytics-monetary.readonly` — and the CLI's own `auth` command may
request only a subset (`yutu auth` omits analytics), so mint the token yourself.

Sensitive-scope warnings on this page are informational for a single-user app; no review is
required when only your own account is a user.

## 2. Branding — the minimum that publishes

Required: **App name**, **user support email**, **developer contact email**. Optional and
best left **empty**: logo, home page, privacy link, terms link — each one pulls in more
publication requirements.

BUT: any app whose scopes are sensitive (YouTube included) will not publish until the
**App domain** block is filled:

- Application home page → live URL you control
- Application privacy policy link → live URL you control
- Application Terms of Service link → optional, but cheap to add
- Authorised domains → the **bare hostname only**: no scheme, no path, no trailing slash
  (`example.com`, not `https://example.com/`). One line covers its subdomains.

## 3. Authorised domains are checked against ownership

Publishing fails with *"not registered to the user"* when the URL's domain is not one Google
can attribute to you. Consequences:

- **`github.com/<org>/<repo>/blob/main/privacy.md` can never pass.** A file host is not a
  registered domain, and a blob URL is not a site. Never put one there.
- A free static host works only after the domain is verified: add a **Domain property** in
  Search Console (`https://search.google.com/search-console` → Add property → Domain) and
  publish the TXT record it gives you at the DNS provider. Domain properties cover every
  subdomain, so one verification covers `ops.example.com` and `example.com`.
- A failed publish starts a **~24 hour retry cooldown**; do not click retry hoping. Finish the
  fix (domain verified, pages returning 200), then choose *request reverification*.

## 4. Serving the policy pages — check the host before choosing a path

Probe the host first; do not assume a folder works:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://target.tld/zzz-not-a-page-12345/
curl -s https://target.tld/zzz-not-a-page-12345/ | grep -oiE "<title>[^<]*"
```

If an invented path returns **200 with the site's own index.html**, the site is a SPA with a
catch-all rewrite: files dropped in `public_html/<folder>/` will be shadowed and the consent
screen will show the shop, not the policy. Use a **subdomain pointed at its own docroot**
(`ops.example.com`) instead of a path, then confirm each URL returns 200 with the expected
`<title>` before submitting it to Google.

## 5. Sequence that works

1. Scopes declared (all of them, once).
2. Policy pages live and curl-verified: 200 + correct title, no placeholder contact address.
3. Domain verified in Search Console.
4. Branding App domain filled with the three live URLs + bare hostname.
5. Audience → **Publish app** → Confirm. Status chip flips `Testing` → `In production`.
6. Only now mint the long-lived token; then re-verify with a real API call (a channel list, a
   one-day analytics query) rather than trusting the token file's existence.

Unverified production apps still work for their own users — the consent screen shows one
"Google hasn't verified this app → Advanced → Go to app" warning. That is normal and not a
failure signal.

## Reusable assets on this host

A styled, scope-accurate page set (home / privacy / terms, no external deps) is kept at
`C:/Users/rest/.youtube-ops/branding/site/`. Replace the `mailto:` contact before uploading —
a live URL with a placeholder address is sloppy on a page Google may crawl.
