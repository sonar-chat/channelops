# Vetting an agent tool candidate (GitHub CLI / MCP) before recommending it

The operator asks "which of these repos is actually right for us". A README tour is not an
answer; the deliverable is a ranked shortlist where every claim is either measured here or
marked unproven.

## 1. Scan by role, not by keyword

GitHub search, sorted by stars, several phrasings at once — a single query hides the category:

```bash
for q in "<topic>+mcp" "<topic>+cli" "<topic>+agent+skill" "<topic>+no+api+key"; do
  curl -s "https://api.github.com/search/repositories?q=${q}&sort=stars&order=desc&per_page=8" \
  | python -c "import sys,json;[print(r['stargazers_count'], r['full_name'], r['pushed_at'][:10], r['language'], '::', (r['description'] or '')[:130]) for r in json.load(sys.stdin).get('items',[])]"
done
```

Read `pushed_at` as hard data: a repo untouched for most of a year is a liability regardless
of stars. Unauthenticated search is rate-limited to a few calls per minute — space the queries.

## 2. Read the source, not the search snippet

`raw.githubusercontent.com/<owner>/<repo>/main/README.md` (fall back to `master`, then hit the
API for the default branch). When a hosted extractor is unavailable, raw fetch is the reliable
path — a docs-level fetch service failing is not evidence the repo is unreachable.

Grep the README for the decision-bearing lines rather than reading it whole:
`api key|api_key|oauth|install|npx|uvx|pip |requires|quota`. The install line tells you the
real dependency weight; the auth line tells you whether the tool is self-contained.

## 3. Red flags that end the evaluation

- **Paid API reseller dressed as a skill.** Setup asks the *agent* for an email, an OTP and an
  `sk_` key, then bills credits per call. Adds a vendor dependency, a billing surface and a
  third-party copy of the data. Reject when a local binary does the same job.
- **GUI-gated MCP.** Needs a desktop app running and a human clicking "Allow" per client, or
  answers only on a localhost port while its window is open. Unusable for cron/detached work.
- **Paper-thin repo for a write-plane job.** Right feature list, single-digit stars, weeks old.
  Fine to mention; never the backbone of anything that touches a live account.
- **Wrong job class.** Channel-management suites ranked against transcript readers (or the
  reverse) produce a confident, useless recommendation — establish the plane first.

## 4. Prove it by running it

Install into the box and execute the candidate before it appears in a recommendation as
"verified":

```bash
<install>            # npm i -g / uvx --from / pip install
<tool> version       # build/config sanity
<tool> --help        # the real command surface
<tool> <verb> --help # the exact flags you will document
```

Anything you cannot install or authenticate is described as **unproven**, with the one human
step that would unblock it named explicitly (e.g. an OAuth client secret only the operator can
create). Never present README-quoted flags as tested behaviour.

## 5. Write the recommendation

Ranked, one short block per candidate: what it does that the others do not, the measured
numbers (search/list latency, star count, last push), the disqualifying property if any, then
the single pick, its honest gap, and the blocker a human must clear. Finish with the artefacts
you already installed so the next session starts from working state, not from the same research.

## 6. Encode the winner, don't re-derive it

After a pick lands, put its verified invocations in the owning skill (or create the class-level
skill if the job class is new) with the pitfalls that cost time — quota math, auth mode, the
platform-specific invocation quirk. The next session should never repeat this scan.
