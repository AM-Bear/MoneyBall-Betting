# DECISION — the ESPN 403 and the shared User-Agent

**Recommendation: point `ESPN_NEWS_URL` at `site.web.api.espn.com` (one line,
`backend/feeds.py:38`) and leave `USER_AGENT` exactly as it is — because the premise of
this decision has expired: ESPN now 403s *every* User-Agent from our egress, so no UA
change unblocks anything, and the measured blast radius of ESPN headlines is zero pulse
movement on all 30 teams today (worst case 2 of 30 teams, −10 points max).**

Written 2026-08-24 by the analysis lane. Read-only: nothing in `backend/` was modified;
`USER_AGENT` is unchanged in the working tree; all probing ran from scratch scripts outside
the repo. Decision is Asher's.

---

## 1. Current state — the brief's premise no longer holds

`notes/v3-plan.md` (Tier 2) and `notes/mlb_api_transcripts.md` §9b both record that ESPN
returns **403 to our UA and 200 to httpx's default**, isolated header by header. That result
**does not reproduce today.** Re-run just now from this workspace:

```
$ python scratchpad/probe.py            # httpx 0.28.1, same client construction as feeds.py
ESPN news      | app client headers   | HTTP 403 |     434 bytes | sent UA: MONEYLINE/1.0 (statistical research terminal)
ESPN news      | UA only              | HTTP 403 |     434 bytes | sent UA: MONEYLINE/1.0 (statistical research terminal)
ESPN news      | httpx default        | HTTP 403 |     434 bytes | sent UA: python-httpx/0.28.1     <-- was 200 in §9b
MLB schedule   | app client headers   | HTTP 200 |   12749 bytes
MLB schedule   | httpx default        | HTTP 200 |   12749 bytes
MLB teams      | app client headers   | HTTP 200 |   23219 bytes
MLB teams      | httpx default        | HTTP 200 |   23219 bytes
MLB RSS        | app client headers   | HTTP 200 |   16254 bytes
MLB RSS        | httpx default        | HTTP 200 |   16254 bytes
```

Widening the UA sweep — bare `curl`, a full Chrome UA, Chrome + `Accept-Language` +
`Referer: https://www.espn.com/` — all 403. Both `/news` and `/scoreboard`:

```
news        | UA=<httpx default>   | 403 | 434b   server=AkamaiGHost
news        | UA=curl/8.5.0        | 403 | 434b   server=AkamaiGHost
news        | UA=Mozilla/5.0 …Chrome/126…        | 403 | 436b   server=AkamaiGHost
news        | UA=Chrome + Accept-Language + Referer | 403 | 434b  server=AkamaiGHost
scoreboard  | UA=Mozilla/5.0 …Chrome/126…        | 403 | 442b   server=AkamaiGHost
scoreboard  | UA=<httpx default>   | 403 | 440b   server=AkamaiGHost
```

The body is an Akamai edge denial, not an ESPN application response:

```
<H1>Access Denied</H1>
You don't have permission to access "http://site.api.espn.com/apis/site/v2/sports/baseball/mlb/news" on this server.
Reference #18.d04ddb17.1787549175.6d840652
```

DNS explains it. `site.api.espn.com` is fronted by Akamai; the block is at that edge:

```
$ getent hosts site.api.espn.com
23.46.228.137   a1526.g1.akamai.net site.api.espn.com site.api.espn.com.edgesuite.net
```

Egress IP at time of test: `136.67.104.184`. Five consecutive requests, all 403, median
46 ms — a deterministic edge rule, not a flaky or rate-limited response.

**So: the User-Agent is no longer the discriminator.** Whatever §9b measured this morning,
the current denial is applied to this egress regardless of headers. Options (b) and (c) in
the brief — per-host UA and a global UA change — are now **verified no-ops for ESPN**. They
cannot buy a single headline.

### The finding that reopens the decision: a different ESPN host answers

The same API is served by `site.web.api.espn.com`, which resolves to ESPN's AWS origins
rather than the Akamai edge, and it answers **200 to the MONEYLINE User-Agent**:

```
$ getent hosts site.web.api.espn.com
44.230.115.194  site.web.api.geo.hosted.espn.com site.web.api.espn.com   (+7 more AWS A records)

site.web.api.espn.com | app client headers   | HTTP 200 | 34207b | 6 articles
site.web.api.espn.com | httpx default        | HTTP 200 | 34207b | 6 articles
repeat codes: [200, 200, 200, 200, 200]  median 29ms  max 111ms
```

It is genuinely ESPN — the TLS cert is `CN=www.espn.com`, `O=The Walt Disney Company`, and
`site.web.api.espn.com` is an explicit SAN on it. The payload shape is byte-identical to
what §9 assumed and `get_news()` already parses: `articles[].headline`, `.published`,
`.dataSourceIdentifier`, `.links.web.href`. **34207 bytes — exactly the size §9b recorded
for its 200.** No parsing change is required.

This is the option the brief did not know existed, and it is the only one that actually
works.

---

## 2. Blast radius — measured, not guessed

Measured by running the **unmodified production code path** (`feeds.get_news` →
`wire.get_wire` → `wire.get_team_pulse` → `analytics.score_pulse_items`) twice against the
live MLB API and the live Postgres record, with only the ESPN host constant redirected
in-process. Against current `main` behaviour, i.e. **after** the `bb4d90f` lexicon
double-count fix (`_drop_subsumed` at `backend/analytics.py:250` is present and active).

### Item counts

| | items | by source |
|---|---|---|
| `get_news()` ESPN off (production today) | 25 | MLB.COM 25 |
| `get_news()` ESPN on | 31 | MLB.COM 25, **ESPN 6** |
| full merged wire, ESPN off | 175 | MLB.COM 25, TRANSACTION 107, DESK 43 |
| full merged wire, ESPN on | 181 | **ESPN 6**, MLB.COM 25, TRANSACTION 107, DESK 43 |

Exactly +6, no dedupe collisions (`wire.py:120-128` drops nothing). Attribution is
`"source": "ESPN"` with `id: "espn-<dataSourceIdentifier>"`, `type: "NEWS"`, `team: null`,
and a live `espn.com` link — `feeds.py:600-613`. `sources_up.news` is unaffected either way,
because the ESPN failure is swallowed *inside* `get_news` (`feeds.py:616-619`).

### Per-team pulse delta — production configuration (6 ESPN articles)

| TEAM | pulse off | pulse on | **Δ** | scanned off→on | pos | neg |
|---|---|---|---|---|---|---|
| ATL | −100 | −100 | **0** | 6 → 7 | 0→0 | 1→1 |
| CHC | −78 | −78 | **0** | 8 → 9 | 1→1 | 8→8 |
| MIL | −33 | −33 | **0** | 5 → 6 | 1→1 | 2→2 |
| SEA | −50 | −50 | **0** | 6 → 7 | 1→1 | 3→3 |
| *all other 26 teams* | — | — | **0** | unchanged | — | — |

**Headline number: 0. Zero of 30 teams move. Four teams gain one scanned item each; none of
those items matches the lexicon, so no score changes at all.**

The mechanism is structural, not luck. ESPN items arrive with `team: null`
(`feeds.py:606`), so they reach a team's pulse only through `wire._item_mentions`
(`wire.py:158-162`), which matches the **full** club name ("Seattle Mariners") in the
headline text. ESPN's recap and analysis headlines use nicknames ("Mariners", "Cubs"), so
they never enter any team's pulse. The only ESPN headlines that carry full names are the
boilerplate `"X vs. Y: Game Highlights"` video clips — which contain no lexicon words by
construction. For reference, **0 of today's 25 MLB.COM headlines match a full team name
either**; the pulse today is almost entirely transaction- and desk-note-driven.

### Worst-case bound (forced `?limit=50`)

`get_news()` sends no `limit`, so production sees ~6 articles. Forcing 50 bounds the
exposure rather than sampling it:

| TEAM | pulse off | pulse on | **Δ** | new scoring evidence |
|---|---|---|---|---|
| **SEA** | −50 | **−60** | **−10** | ESPN: *"Seattle Mariners put Brendan Donovan on 7-day concussion IL"* → neg `il` |
| **ARI** | −54 | **−57** | **−3** | ESPN: *"Arizona Diamondbacks place Michael Soroka on injured list"* → neg `injured` |
| *other 28 teams* | — | — | **0** | 23 gain 1 scanned item, 0 scoring |

**Worst case: 2 of 30 teams move, largest move −10 points, both from real IL news that is
already true and already in the MLB transactions feed under a different wording.**

Base rates over that 50-headline sample: 15/50 contain a full club name; 12/50 hit the
lexicon; only **2/50 do both** and can therefore move a pulse at all.

### Latency, the one non-display cost

If ESPN starts answering, the one-shot latch (`feeds.py:182`, `593-594`) never fires, so
every ~30-minute `wire_source_cache` miss makes one extra outbound call on `/api/wire` and
`/api/team-live`. Bounded by `FEED_TIMEOUT_SECONDS` (10s) and the 25s cache deadline;
measured at 29 ms median today. It is a real but small addition to first-request latency on
those two routes, and it self-heals — one failure re-latches ESPN off for the process.

---

## 3. Doctrine — can an ESPN headline reach a price? No. Traced.

`replit.md` states media pulse is disclosed context that **never** moves a price. Verified
independently, by call graph rather than by assertion:

**Forward trace from the ESPN item.** `feeds.get_news()` (`feeds.py:567`) is called from
exactly one place in the codebase: `wire.get_wire` (`wire.py:113`). `wire.get_wire` and
`wire.get_team_pulse` are imported by exactly one module, `backend/main.py:80`, and used at
exactly two call sites: `/api/wire` (`main.py:1007`) and `/api/team-live/{team_id}`
(`main.py:1055`). Neither route computes or returns a price — `/api/team-live` returns team
data plus `flags` and `pulse`, stamped with its own hard rule at `main.py:1062`.
`analytics.score_pulse_items` (`analytics.py:234`) has exactly one caller,
`wire.py:176`.

**Reverse trace from the price.** The price chain is `feeds._chain_probability`
(`feeds.py:302`) → `_blended_side` (`feeds.py:854`) → `_price_game` (`feeds.py:315`) →
`get_slate` (`feeds.py:445`), plus `inference.predict_from_inputs` and `odds.*`.
`backend/feeds.py` **does not import `backend.wire`** — the dependency runs one way only
(`wire.py:15-21` imports feeds; nothing imports wire except `main.py`). A circular import
would be needed for a headline to reach a price, and there is none. Same for
`odds.py`, `analytics.py`, `inference.py`, `season_sim.py`, `players.py`, `precompute.py`:
none imports `wire`.

**Frontend.** `pulse-meter.tsx` reads `pulse.pulse`, `.items_matched`, `.evidence`,
`.method`, `.hard_rule` and renders a chip; it performs no arithmetic on any price.
`pricer-panel.tsx:267` mounts it as a sibling of the price display, not an input to it.

**Conclusion, plainly: the blast radius is display-only.** An ESPN headline can change one
number a reader sees on a team chip, and nothing else. No graded pick, no fair line, no
parlay, no playoff probability, no record entry can move. That materially shrinks this
decision — it is a *content curation* call, not a *model integrity* call.

---

## 4. Options

### (a) Leave it blocked, keep the silent-skip path

- **Files changed:** none.
- **Breaks:** nothing. The latch at `feeds.py:182/593-619` is already doing its job
  correctly, `sources_up.news` stays `true`, the wire carries 25 MLB.COM headlines.
- **User sees:** exactly what they see today.
- **Caveat:** the notes are now wrong. `notes/v3-plan.md:83-88` and
  `notes/mlb_api_transcripts.md` §9b both attribute the 403 to our User-Agent. That is no
  longer true, and the doctrine is receipts. If (a) is chosen, §9b needs an addendum
  recording today's measurements, or the next session re-litigates a UA that was never the
  problem.

### (b) Per-host User-Agent — ESPN gets a default-looking UA, MLB keeps the honest one

- **Files changed:** `backend/feeds.py:596`, one line:
  `espn = await client.get(ESPN_NEWS_URL)` →
  `espn = await client.get(ESPN_NEWS_URL, headers={"User-Agent": "python-httpx/0.28.1"})`.
- **Mechanically clean — verified.** httpx merges per-request headers over client headers,
  same key wins, and other calls are untouched:
  ```
  override UA -> python-httpx/0.28.1
  default  UA -> MONEYLINE/1.0 (statistical research terminal)
  RSS-style call keeps UA -> MONEYLINE/1.0 …  | accept: application/xml
  ```
  The existing RSS call at `feeds.py:575` already uses this exact pattern for `Accept`, so
  it is idiomatic in this file. MLB's API is verified indifferent to the UA either way
  (200 with both, identical byte counts), so leaving `USER_AGENT` in place costs nothing.
- **Breaks:** nothing.
- **User sees: nothing. This option does not work any more.** `site.api.espn.com` 403s the
  httpx default UA today. Measured above. It would ship a UA lie and still get zero
  headlines.

### (c) Change the shared `USER_AGENT` globally

- **Files changed:** `backend/feeds.py:33`.
- **Reach:** every `statsapi.mlb.com` call — all 13 `_fetch_json` sites plus the RSS fetch —
  since they all share `_get_client()` (`feeds.py:185-193`).
- **Breaks:** nothing functionally; MLB is verified indifferent.
- **User sees: nothing. Also a no-op for ESPN today.** Strictly worse than (b): same zero
  benefit, but it surrenders the honest identifier on every MLB request too.

### (d) Switch the ESPN host — **the only option that actually unblocks ESPN**

- **Files changed:**
  - `backend/feeds.py:38` — `ESPN_NEWS_URL = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/news"`
    → `"https://site.web.api.espn.com/apis/site/v2/sports/baseball/mlb/news"`.
  - `backend/feeds.py:34-36` — the comment above it cites §8/§9; it should cite the new
    §9c transcript and say why the host differs.
  - `tests/test_news_feed.py:98` — `assert feeds.ESPN_NEWS_URL.startswith("https://site.api.espn.com/")`
    **fails** under this change. It must become `"https://site.web.api.espn.com/"`. This is
    the only test that breaks; the other five in that file pass unchanged (they stub the
    client and key off `feeds.ESPN_NEWS_URL` by identity, `test_news_feed.py:74,149`).
  - `notes/mlb_api_transcripts.md` — new §9c with today's transcripts.
  - `notes/v3-plan.md:83-88` — the Tier 2 ESPN paragraph is now factually wrong.
- **No parsing change.** Payload shape is identical; `feeds.py:598-613` works as written.
- **Breaks:** nothing measured. Repeat probes 5/5 × 200. Note the host has no retrievable
  `robots.txt` (403), and `www.espn.com/robots.txt`'s `User-agent: *` block does not
  disallow `/apis/`.
- **User sees:** +6 wire items/refresh attributed `ESPN` with working links; **zero pulse
  movement today**, worst case 2 teams and −10 points. Plus the small latency note in §2.

---

## 5. The honesty angle

The doctrine is receipts and refusals over fake precision. Three distinct questions hide
inside "is this consistent with that", and they deserve separate answers.

**Presenting a browser/default UA to dodge a 403 — option (b) or (c).** The case *for*: a
User-Agent is a courtesy string, not an authentication token; the endpoint is public,
keyless, and unauthenticated; the v2 spec itself sanctions ESPN as a source; and there is no
downstream claim of precision being faked — a headline is a headline. The case *against*:
MONEYLINE's whole posture is that it says what it is. `"MONEYLINE/1.0 (statistical research
terminal)"` is a deliberate act of self-identification, and swapping it for
`python-httpx/0.28.1` specifically because the honest string got refused is, precisely,
misrepresenting who is calling in order to obtain something that was denied. An app that
refuses to invent a hitter-vs-pitcher number because it cannot honestly compute one should
not be comfortable inventing an identity because it did not like the answer. **This
argument is now moot in practice — neither UA gets in — but it should be recorded as
settled, so it is not re-opened by the next person who sees a 403.**

**Switching hosts — option (d).** Weaker on both sides, and honestly so. It is *not*
identity misrepresentation: the request still says "MONEYLINE/1.0 (statistical research
terminal)", to a documented public ESPN host, with a valid ESPN certificate, and if ESPN
wants to refuse that string it can, on any host. That is the substance of the honesty
doctrine and it is fully preserved. But it is not nothing either: `site.api.espn.com` is
Akamai-fronted and `site.web.api.espn.com` is not, so choosing the second is choosing the
door where the guard is not standing. Whether ESPN intended a blanket block on this egress
or merely has an inconsistently-configured edge, we cannot know from outside. The
honest framing is: **we identify ourselves truthfully and use a public endpoint that accepts
that identification.** If ESPN later blocks that host too, the correct response is (a) —
latch off and move on — not another host hunt.

**The third question, and the one that most deserves an answer: is it worth it?** ESPN buys
6 headlines a refresh, mostly auto-generated recaps and "Game Highlights" video stubs, that
by measurement change no number a reader sees. The MLB.com RSS feed already carries 25. The
spec's own words are "must never be a dependency". A reasonable person could look at a
measured delta of **zero** and conclude the honest move is (a): don't route around a block
for content that demonstrably does not matter. That is a defensible read of the same
evidence, and it is Asher's call to make.

---

## 6. Recommendation

**Take (d), plus the documentation half of (a).**

Reasoning, in order of weight:

1. **(b) and (c) are dead.** They are the two options the parked decision was actually
   about, and both are now measured no-ops. Whatever is decided, they should be struck.
2. **The doctrine cost of (d) is genuinely low and the doctrine benefit is real.** The
   identifying UA — the thing worth protecting — stays. The alternative interpretations of
   "honest" cut both ways here, and truthful self-identification is the one the codebase
   actually encodes.
3. **The measured product change is zero today and −10 points on one team in the worst
   case, on a number that provably cannot reach a price.** This was parked as a "visible
   product change". It is a display-only change of measured magnitude zero. That is a much
   smaller thing than the parking note assumed.
4. **The notes must be corrected regardless of the decision.** `notes/v3-plan.md:83-88` and
   `notes/mlb_api_transcripts.md` §9b assert a UA-causation that today's transcripts
   disprove. A codebase whose selling point is receipts should not carry a stale one. This
   half is not optional under any option.

If Asher would rather not route around an edge block on principle — a position I think is
defensible — then take **(a) with the §9c addendum**, and close (b) and (c) permanently with
today's evidence so nobody re-opens them.

Either way: **do not change `USER_AGENT`.** It buys nothing, and it costs the one thing in
this decision that was actually worth defending.

---

## 7. What I could NOT verify

- **Whether the Deploy runtime sees the same 403.** Everything here ran from this
  workspace's egress (`136.67.104.184`). The Akamai denial is plausibly IP- or
  ASN-scoped, so a deployed Repl on a different egress might still get 200 from
  `site.api.espn.com`. If that matters, the check is one `curl` from the deployed
  container — Asher's step, not mine.
- **Why §9b measured 200 to the httpx default this morning and I measure 403 now.**
  Both readings are recorded honestly. Candidate explanations — an Akamai rule rolled out
  today, an IP-reputation trip caused by the volume of probing across sessions, or a
  geo/edge-node difference — cannot be distinguished from outside. If it is
  reputation-based, it may decay; option (d) is unaffected either way, since it never
  touches the Akamai edge.
- **Durability of `site.web.api.espn.com`.** Verified over ~10 requests in one sitting, not
  over days. It is an undocumented public host and ESPN owes us nothing; it could be
  blocked or retired at any time. The silent-skip latch is exactly the right guard for that
  and stays in place under every option.
- **Multi-day pulse behaviour.** The delta table is one day's wire (2026-08-24) plus a
  50-headline worst-case bound. The *mechanism* generalises — ESPN items carry `team: null`
  and mostly use nicknames, so they cannot enter a team pulse — but the specific −10 on SEA
  is a single observation, not a distribution.
- **Nothing was run against the live api-server.** No workflow was restarted and no route
  was called over HTTP; the measurements import `backend.*` directly in-process.
