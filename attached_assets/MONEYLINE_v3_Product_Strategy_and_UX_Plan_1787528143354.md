# MONEYLINE v3 — Product Strategy and UX Redesign

**From trading terminal to research desk for everyday bettors, without losing the math**

Prepared for: Asher (MONEYLINE)
Role: senior product design, UX strategy, sports-betting analytics product review
Date: August 23, 2026
Status: strategy draft for discussion, followed by an implementation plan (Part 2)

---

## How to read this document

Part 1 (sections 1–17) is the product strategy in the format you requested. Part 2 converts the highest-priority recommendations into a concrete UI/UX implementation plan organized by page, component, data requirement, user flow, and acceptance criteria. The appendices hold the specifications engineering will need verbatim: the verdict engine (A), the explanation generator (B), stake sizing (C), the copy rules (D), analytics (E), and the migration map (F). The terminology dictionary is in section 8.2 and the API additions are in Part 2.

Every major recommendation carries a five-line assessment block — the user problem it solves, why it improves usability, which advanced information it preserves, how it affects trust, and how hard it is to implement. Effort is rated Low (days), Medium (one to three weeks for one engineer plus design), or High (a month or more, or a new data dependency).

### What this strategy assumes about the current product

The strategy is grounded in the v1 build spec, the v2 expansion spec, and the total-smoke-test spec in your project. Those documents establish facts that shape the recommendations below, so they are worth restating.

The model is the Moneyball regression stack: runs scored from OBP and SLG, runs allowed from opponent OBP and SLG, wins from run differential, playoff odds from wins, trained on 1962–2012 team seasons with a chronological split. Games are priced by turning each team's predicted runs into a Pythagorean strength and combining the two with log5. Two prices exist per game: the **season price** (season-to-date team inputs) and the **starter-adjusted price** (the probable starter's OBP-against and SLG-against blended into the team's run-prevention inputs). The Live Record grades both, in public, every day.

The doctrine is explicit and I treat it as non-negotiable: every number on screen is real and traceable; advice must be earned by a track record, never claimed in advance; injury flags and media pulse are disclosed context and never move a price; the app never urges a wager.

Three facts matter enormously for the redesign and are easy to miss:

1. **There is no sportsbook odds feed.** Book lines are entered manually in the Edge Finder. Several of your proposed ideas (book price on every card, edge on every card, "compare sportsbook prices") cannot exist at scale without one. The strategy treats a licensed odds feed as a Phase 1 dependency and designs an honest fallback for when a price is missing.
2. **The pricing chain has no home-field adjustment and no recent-form input.** Two of your proposed explanation categories ("home/away performance", "recent form") describe things the model does not price. They can appear only as context, never as reasons the model leans a side, until they are added to the model and graded like the starter adjustment was.
3. **The model is season-level.** The v1 spec says it plainly: a season-aggregate model has not yet earned a game-level edge against closing lines. The redesign must make the product feel confident and usable without pretending this has changed. The only thing allowed to change it is the graded record.

Other working assumptions: the platform remains a responsive web app (FastAPI + React on Replit) with a progressive web app as the mobile strategy before any native app; the sport remains MLB for now; the market is the United States with a 21-and-over audience; the product will charge money, which raises the bar on data licensing and consumer-protection language.

### Vocabulary used throughout

| Term | Meaning in this document |
|---|---|
| **Verdict** | The one-line answer a card gives about a game side: *Bet candidate*, *Marginal value*, *No value detected*, *Avoid at this price*, or *Insufficient data*. Produced by a deterministic, published rule set (Appendix A). |
| **Lean** | The side the model prices above 50%. A lean is not a recommendation; it exists for every game. |
| **Value side** | The side, if any, whose sportsbook price is better than the model's fair price. It is frequently not the lean. |
| **Signal strength** | How far the model's price sits from the book's, relative to the model's typical error. Measures disagreement, not certainty. Three levels: *Strong*, *Moderate*, *Weak*. |
| **Detail level** | A user preference, *Essentials* or *Full detail*, that sets how much each screen shows by default. It never changes a verdict. |
| **Priced** vs **context** | *Priced* information is an input to the model's probability. *Context* is information the app discloses but does not price (injuries, news pulse, home/away, weather). The distinction is visible in the UI. |

---

## 1. Executive recommendation

MONEYLINE's asset is not its terminal aesthetic. Its asset is a doctrine most betting products cannot match: every number is real, every price shows its arithmetic, "no value" is a normal result, and the model grades itself in public. The redesign should keep every part of that doctrine and change only the delivery — from a dense screen that assumes the reader already knows what vig and Kelly are, to an answer-first experience that tells an everyday bettor what the model thinks, whether the price is worth it, why, and what it would cost to be wrong, with the full mathematics one tap away for anyone who wants it.

The recommendation comes down to six moves.

**First, replace the Desk with a Today dashboard built on a verdict engine.** Every game becomes a card that answers your seven questions in order: attention, lean, price, edge, why, risk, action. The verdict ("Bet candidate", "No value detected", "Insufficient data") is the headline, not the lean, because a lean without a favorable price is not actionable and presenting it first is how analytics products quietly become tout products. The rules that produce verdicts are published inside the app and the Track Record reports how each verdict and signal-strength bucket has actually performed.

**Second, build one card system with progressive disclosure instead of two modes.** "Beginner" and "Advanced" as global modes create two products to maintain and a label nobody wants to self-select. The better structure is a single card whose three layers — answer, explanation, numbers — are always present, plus a *detail level* preference (Essentials or Full detail) that sets default expansion, and an independent *explain terms* toggle for inline definitions. Experts get density; newcomers get clarity; both see the same verdict computed the same way.

**Third, add a licensed odds feed and make prices first-class data.** This is the single most important missing piece. Without live prices there is no automatic "is the book price favorable?", no line shopping, no closing-line value, and the Live Record's units are booked at a flat −110 assumption instead of real prices. An odds feed converts the model from a curiosity into a daily tool, and it converts the track record from "hit rate" into the metric serious bettors actually trust: performance against closing prices.

**Fourth, make bankroll the frame for every stake, and shrink the model's edge before sizing.** Users set a bankroll and a risk profile once; every candidate then shows a dollar-sized *model stake* with the Kelly arithmetic beneath it. Because the model's game-level edge is unproven, the staking probability blends the model's estimate with the market's de-vigged probability before Kelly is applied, and profiles cap the stake at 1–3% of bankroll. Responsible-use tooling (limits, loss reminders, paper mode by default, no urgency notifications) is part of the feature, not a settings afterthought.

**Fifth, promote the Track Record to a primary destination and make it the marketing home page.** Backtests, live paper picks, user-entered bets, and graded picks are four different things and get four visually distinct treatments. The page states what the numbers prove, what they do not, and how many bets it would take to know — roughly 1,600 bets to be reasonably sure of a 5% return, roughly 4,400 for 3%. A product that says this out loud is more credible than any product that does not.

**Sixth, refresh the visual system toward "analytics dashboard meets personal-finance app".** Keep the analytical personality (tabular numerals, a monospace face reserved for prices, the ◆ mark, restraint) and drop the terminal furniture (uppercase everything, monospace everything, saturated green/red, blinking indicators, boot sequences). Verdict colors are desaturated and paired with icons and words; wins and losses are recorded, not celebrated. Both a refined dark theme and a light theme come from the same token set.

Three of the proposed ideas should be delayed or reframed. The "model slip of the day" parlay should not appear on a broad-audience product until the parlay record has enough graded slips to say something; an "Aggressive" risk profile should be renamed and capped; and "Find an Edge" as a navigation label should not ship, because it promises a daily edge the doctrine does not allow the product to claim.

The commercial shape is freemium: the Today dashboard's verdicts, the full Track Record, and all education are free because they build trust; live prices across books, full breakdowns, bankroll sizing, closing-line-value tracking of your own bets, parlay checks, and alerts are the paid tier. A realistic delivery is three phases over roughly 16–20 weeks, with the Today dashboard, odds feed, verdict engine, and public Track Record shipping first.

---

## 2. Target users and positioning

### 2.1 Who this is for

The broad audience is not one audience; it is three, and the product should be designed for the first, retained by the second, and evangelized by the third.

**Primary — the regular recreational bettor.** Bets a few times a week on one or two sportsbook apps, usually $10–$50 a game, often in parlays, mostly on favorites and familiar teams. Has heard "line shopping" and "expected value" but could not define vig. Frustrated by tout culture and by the feeling of betting on vibes, and would pay a streaming-service price for a tool that makes the decision feel researched. Needs answers first, arithmetic second, and needs "pass" to feel like a good outcome rather than a missed opportunity. This is the user the seven questions were written for.

**Secondary — the disciplined semi-serious bettor.** Tracks bets in a spreadsheet, shops two or three books, knows fractional Kelly, and judges any model by its record against closing lines. Will not pay for verdicts alone; will pay for a transparent model as a second opinion, for closing-line-value tracking of their own bets, for the receipts, and for a research desk that does not insult them. This user is the retention and word-of-mouth engine, and the reason nothing advanced may be removed.

**Tertiary — the baseball analytics fan.** May bet rarely or never. Comes for the BA paradox, the player percentiles, the rest-of-season simulation, and the honesty. Produces content, screenshots, and referrals. Needs research surfaces to remain excellent and needs the app to not feel like a sportsbook.

**Explicit non-targets.** People looking for picks and locks (the product will disappoint them on purpose); professional bettors running their own models (they may use MONEYLINE as one input but will not be the core); anyone under 21.

### 2.2 The jobs to be done, mapped to your seven questions

| User question | What the product must show | Where |
|---|---|---|
| Which games deserve my attention? | A daily summary and cards sorted by verdict, with "nothing here today" as a legitimate outcome | Today |
| Which side does the model prefer? | The lean and the model chance for both sides | Card header |
| Is the sportsbook price favorable? | Best available price vs the model's fair price, with the book named and the time stamped | Card price row |
| How strong is the potential edge? | Edge in points and expected return per $100, plus signal strength | Card edge row |
| Why does the model prefer this side? | Three plain-English reasons generated from the model's own receipts, clearly separated from context it does not price | Card "Why" layer |
| How much risk is involved? | Chance the bet loses, payout shape, model uncertainty, and stake as a share of bankroll | Card risk row; stake card |
| Consider, pass, or investigate? | The verdict and a single call to action, "See full breakdown" | Card header and footer |

### 2.3 Positioning statement

> **MONEYLINE is the honest research desk for baseball bettors.** It prices every game with a transparent model, compares that price with the sportsbook's, tells you plainly when there is nothing worth betting, and grades its own record in public. Research, not picks.

Supporting claims the product can make today, without overreach: every number traces to public data or a stated formula; the model shows its arithmetic on every price; the record is graded daily against real final scores and is never edited; "no value" is the most common verdict, and the product says so.

Claims the product must not make until the record earns them: that the model beats the books; that any verdict wins at any rate; that a signal-strength label predicts outcomes. The Track Record page is where those claims are tested, and the copy rules in Appendix D keep them out of everywhere else.

### 2.4 Competitive frame

Against pick-selling services, MONEYLINE's differentiator is that it refuses to sell certainty and publishes losses. Against odds-screen products (line-comparison and positive-EV scanners), its differentiator is a model with receipts and explanation — those products tell you that a price is off-market, not why a team is good — and a friendlier reading experience. Against the spreadsheet a disciplined bettor already keeps, its differentiator is automation: closing-line capture, grading, and a model-derived second opinion. The product should avoid competing on breadth of sports or on odds coverage alone, where incumbents with licensing budgets win.

### 2.5 Monetization sketch

| Tier | Includes | Rationale |
|---|---|---|
| Free | Today dashboard with verdicts and leans; one book's price per game or manual entry; full Track Record; education center; research desk (players, teams, season) with daily limits | Trust is built on the free tier. The record and the education must never sit behind a paywall or the honesty claim collapses. |
| Pro (subscription) | Prices across multiple books with best-price flagging; full breakdowns with receipts; bankroll and stake sizing; your own bet log with closing-line value; Parlay Check; alerts; CSV export; unlimited research | These are the features the secondary persona already pays for in fragments across several tools. |

Pricing itself needs testing; the useful anchor is that the primary persona compares it to a streaming subscription and the secondary persona compares it to an odds screen.

### 2.6 What success looks like

Activation: a new user opens a full breakdown within the first session. Comprehension: in usability tests, a primary-persona user can explain what "fair price" and "edge" mean after one session without prompting. Trust: a meaningful share of weekly sessions include a visit to the Track Record. Discipline: the share of stakes placed within profile caps stays near 100%, and the share of users who set a limit grows. Commercial: conversion from free to Pro driven by price comparison and bankroll features, not by hidden verdicts.

---
## 3. What to keep, simplify, and redesign

### 3.1 Critique of the ten proposed ideas

#### Which ideas are strongest

**Idea 1, the Today dashboard, is the product.** It is the right default screen and the right unit of design. The instinct to make each game a card that answers questions in order is correct; what needs to change is the hierarchy (the verdict, not the lean, must lead), the data dependency (a book price on every card requires an odds feed), and the explanation rules (see idea 4). Done well, this one screen carries the repositioning.

**Idea 4, the explainable model summary, is nearly free and enormously valuable.** The app already computes receipts for every price (feature × coefficient → contribution) and already blends starter inputs. A plain-English "why" is mostly a templating layer over numbers that exist. Its value is that it converts a probability into a story a person can evaluate, which is the difference between a tool and an oracle.

**Idea 8, a prominent Track Record, is the differentiator.** No competitor in the primary persona's world grades itself in public and shows its losses. Making that page primary, adding closing-line value once prices exist, and stating what the record proves and does not prove is the most credible marketing the product can do. It should be the public home page for logged-out visitors.

**Idea 3, terminology translation, is the cheapest high-impact change.** Most of the "terminal" feeling comes from labels, not layouts. A single terminology dictionary in code, used by every component, fixes it everywhere at once and keeps the technical term visible for people who want it.

**Idea 7, bankroll-first sizing, is strong for both discipline and revenue,** provided it ships with the guardrails discussed below. Converting a Kelly fraction into "$18 of your $1,000" is the moment the product starts to feel like a finance app rather than a terminal.

**Idea 6, the honest parlay experience, is already the best-designed part of v2.** The vig-compounding strip and the refusal of correlated legs are exactly right. The redesign is a verdict-first layout, a singles-versus-parlay comparison, and a more confident tone when a slip is poor value.

#### Which ideas could confuse users

**Idea 2 as two global modes.** "Beginner" is a label people decline to wear, and a global switch creates two products: screenshots differ, support conversations differ, and a user who toggles it mid-session sees the interface rearrange itself. Per-page toggles are worse (inconsistent state). The recommendation in section 7 is progressive disclosure inside every component, plus one *detail level* preference that sets default expansion, plus an independent *explain terms* toggle. Both audiences see the same verdict, computed the same way.

**"Confidence: Strong" on the example card.** To an everyday reader, "confidence" means "likely to win," and a 58% favorite loses 42% of the time. The metric you want is how far the model disagrees with the market relative to its own error, which is a statement about the price, not about the outcome. Section 6 renames it *signal strength*, defines it on screen, and lets the Track Record show how each level has actually performed.

**"Potential edge +8.4%" on the example card.** The arithmetic in your example is internally inconsistent in a way worth catching now. At a model chance of 58%, the fair price is −138 (the app rounds to −140). At a book price of −115, the implied chance is 53.5%, so the probability edge is +4.5 points; the +8.4% figure is the *expected value per unit wagered* (0.58 × 0.87 − 0.42). Both are useful, but they are different numbers with different labels, and the app's own definition of edge (v1 spec) is the probability gap. Section 8 fixes the vocabulary: **edge** is in points, **expected return** is in dollars per $100.

**"Model lean" as the headline.** The lean is not the value side, and a card that leads with the lean steers readers toward the wrong bet on a regular basis. Take the same game with the model at 58% Boston but a book price of −160: Boston's implied chance is 61.5%, so Boston has negative expected value (about −5.8%), while the Yankees at +140 (implied 41.7% versus a model chance of 42%) are roughly break-even. A lean-first card says "Boston"; the honest answer is "No value on Boston at this price; the Yankees are marginal." The card must evaluate both sides and lead with the verdict.

**"Price value" listed among the reasons the model leans a side.** The price does not change the model's opinion of the team; it changes whether the bet is worth making. Mixing the two makes the explanation incoherent and quietly implies the model reacts to the market. Section 6 splits "why the model leans Boston" from "why this is a candidate."

**"Home/away performance" and "recent form" as explanation categories.** The pricing chain does not include either. If those bullets appear under "why the model leans," they are fiction. They belong in the *context* layer, explicitly labeled "not in the price," until the model adds them as graded experiments.

**Idea 5's eight-item navigation.** Eight top-level destinations do not fit a phone's bottom bar and blur the difference between daily surfaces and research tools. "Find an Edge" duplicates what Today already does when filtered to candidates, and "Team & Season Trends" invites streak-chasing the model does not do. Section 4 proposes five primary destinations and a research hub.

**Idea 9's eight-lesson onboarding.** Delivered up front, it is a course and will be skipped. Delivered contextually, at the moment each concept first matters, it works. Section 12 uses four screens plus coach marks and an education center.

**Idea 3 if implemented as pure renaming.** If "EV" disappears in favor of "expected value per unit wagered" everywhere, the secondary persona loses the vocabulary they search for. Labels must be dual: plain-English primary, technical secondary.

#### Which ideas carry legal, compliance, trust, or responsible-gambling concerns

I am not a lawyer; the items below are product-level flags to raise with counsel, ordered by how much they should shape the design.

**Dollar stake suggestions (idea 7), especially by default in "Beginner mode."** A dollar figure next to a team name is the most advice-like element in the product. Design mitigations: the stake never appears until the user has set a bankroll and a profile; it is labeled "model-sized stake (paper)" until the user records a real bet; it is capped by profile (1–3% of bankroll); it reads "no stake — no value at this price" whenever expected value is not positive; it never appears in notifications or share cards; and the staking probability is shrunk toward the market's price because the model's edge is an estimate (section 10).

**An "Aggressive" risk profile.** The word invites exactly the behavior responsible-gambling frameworks exist to discourage, and full Kelly on an unproven edge is ruinous in practice (the example bet at full Kelly would be 9.7% of bankroll). Rename it "Higher variance," cap it at 3%, and describe its drawdowns.

**Cards that read as a pick sheet (idea 1).** If the Today screen looks like a slate of selections, the product is a tout with better typography. Mitigations: "Bet candidate" is a research label in a neutral pill, never a button; the call to action is "See full breakdown," never "Bet now"; no sportsbook deep links; "No value detected" cards are styled with the same care as candidates; a daily summary states the pass rate.

**"Model slip of the day" (existing v2 feature, implied by idea 6).** A daily featured parlay, however well-receipted, is a daily featured parlay. For a broad audience it reads as a recommendation and it promotes the worst-value bet type. Remove it from default surfaces until the parlay record is large enough to say something, then reintroduce it, if at all, as an educational "least-drag example" inside the Parlay Check page.

**Track-record claims (idea 8).** Publishing a record is the right thing; publishing a record without intervals, sample size, and the −110 flat-odds assumption is a consumer-protection exposure. The record must never mix backtest and live numbers in one figure, must show a confidence interval on ROI, and must state that units are booked at real prices only once prices exist. Marketing copy should quote the record only with these qualifiers.

**"Compare sportsbook prices" and any link to a book.** Showing prices is fine with a licensed feed. Linking to sportsbooks with tracking codes turns the product into an affiliate, which many US states treat as a licensed or registered activity and which advertising codes constrain. Ship v3 with no outbound sportsbook links; if affiliate revenue is ever pursued, do the registrations first.

**Data licensing for a paid product.** The keyless MLB Stats API is a gift for a class project; commercial use needs a review of its terms, and a paid product should budget for a licensed stats and odds provider. This is the one open question that could change the roadmap's cost.

**Age gating, jurisdiction, and responsible-use tooling.** Add a 21+ attestation at signup, responsible-gambling resources (1-800-GAMBLER and the National Council on Problem Gambling helpline) in the footer and in the bankroll area, user-set loss and session limits, a cooling-off switch that hides stakes for a chosen period, and a standing rule that no notification ever creates urgency.

**Simplification that removes honesty.** The subtlest risk in idea 2 is that "Beginner mode" hides sample-size labels, staleness stamps, and the research disclaimer because they look like clutter. Those elements are not collapsible in any mode. Section 14 calls them *honesty furniture* and gives them a permanent place.

**Payment processing.** Some processors classify betting-information services as restricted or high-risk. Confirm with the chosen processor before building billing.

#### Which ideas should be combined

Ideas 1, 2, 3, and 4 are one system, not four features: the card is the unit (idea 1), its three layers are the modes (idea 2), its labels are the terminology (idea 3), and its middle layer is the explanation (idea 4). Building them together avoids four inconsistent implementations.

"Find an Edge" (idea 5) folds into Today as a "Candidates only" filter and a sort-by-edge option, while the existing Edge Finder tool (any two team-seasons, manual price) lives on as *Matchups* inside Research.

Bankroll (idea 7) and the user-entered-bets part of the track record (idea 8) belong together in a *Bankroll* area: your money, your stakes, your logged bets, your closing-line value. The model's record stays in *Track Record*; the two pages link to each other.

Onboarding (idea 9), terminology (idea 3), and the tooltips all draw from one content source — the education center — so a definition reads identically in a coach mark, a tooltip, and a lesson.

Parlay stake caps (idea 6) come from the bankroll profile (idea 7), with a lower cap for parlays than for singles.

The visual refresh (idea 10) is the token system every other idea is built on, so it starts first, not last.

#### Which ideas should be delayed or reframed

| Idea or element | Recommendation | Reason |
|---|---|---|
| Model slip of the day | Delay; reframe later as an educational example | Tout framing; promotes parlays |
| "Aggressive" profile | Reframe as "Higher variance," capped at 3% | Responsible use; Kelly on an estimated edge |
| "Find an Edge" nav item | Do not ship under that name | Promises a daily edge |
| Home/away and recent-form explanations | Delay until priced and graded | Not in the model today |
| Native mobile apps | Delay; ship a PWA first | Same code, faster, no store review of a betting-adjacent app yet |
| Light theme | Build tokens now, ship the theme in Phase 2 | Refined dark first for continuity; both from one token set |
| Multi-book price comparison UI | Phase 2, after the odds feed is stable | Depends on feed reliability |
| Alerts | Phase 3, informational only | Needs accounts; urgency risk |
| Media pulse on cards | Keep behind the context layer only | Lexicon score confuses casual readers without its evidence |
| "Team & Season Trends" | Rename *Teams & Season*; drop "trends" | Avoid streak content the model does not use |

#### What important product ideas are missing

**A licensed odds feed with line capture.** Opening, current, and closing prices per game per book. This enables verdicts at scale, best-price flagging, stale-price warnings, and closing-line value. It is the largest gap between the proposed ideas and a sellable product.

**Closing-line value (CLV) as the trust metric.** Win-loss records need thousands of bets to mean anything; consistently beating the closing price shows up in hundreds. CLV should be reported for the model's paper picks and for the user's own logged bets.

**A published verdict engine.** Users should be able to read the rules that make something a candidate (Appendix A) and see the thresholds. Nothing builds trust like showing the rubric.

**A risk row on every card.** "Chance this bet loses: 42%" reframes a favorite plainly; payout shape and model uncertainty complete the picture. Your brief asks "how much risk is involved?" and none of the ten ideas answers it directly.

**A daily summary with a pass rate.** "15 games · 2 candidates · 9 no value · 4 waiting on data." It makes passing a visible, normal, even reassuring result, and it inoculates against the pick-sheet reading of the page.

**Your own bet log with grading and CLV.** The secondary persona's spreadsheet, automated. It is also the honest bridge from "paper stake" to "real stake."

**Preferred sportsbooks.** Prices are only useful if they are the prices the user can actually get. A setting for the user's books changes which price the card shows and flags when a better price exists elsewhere.

**Line movement versus the model.** Opening price → current price, with the note that when the market moves toward the model the edge shrinks. Serious bettors read this instantly; casual bettors learn from it.

**A model changelog.** Every model change (the starter adjustment, a future home-field term) gets a date and is graded from that date. Trust comes from versioning.

**A home-field adjustment as the next graded experiment.** MLB home teams win roughly 53–54% of games; a pricing chain without a home term is systematically off on home underdogs and road favorites. Add it the way the starter adjustment was added — as a second price the record grades — rather than assuming it.

**Shareable research cards.** An image export of a card with the verdict, the receipts, the sample label, and the research disclaimer baked in. The growth loop for the tertiary persona.

**A responsible-use toolkit** (limits, cooling-off, session reminders, resources) and **accounts, sync, and billing** (prerequisites for anything paid).

### 3.2 Keep, simplify, redesign, retire

| Element | Decision | Notes |
|---|---|---|
| Regression stack, Pythagorean + log5 pricing, receipts | **Keep** | Untouched. The redesign changes presentation only. |
| Season and starter-adjusted dual pricing, graded side by side | **Keep** | Surface as "Season strength" and "With tonight's starters"; the record still decides. |
| Live Record grading, immutability, no deletions | **Keep** | Extend with candidate-only records, CLV, segments, intervals. |
| Refusal states (2027, hitter vs pitcher, no salary data) | **Keep** | Rewrite copy in sentence case; they are trust assets. |
| Context-never-moves-a-price rule | **Keep** | Make it visible: a "not in the price" label on every context chip. |
| Player Desk, Head-to-Head, Season simulation, Screener | **Keep, restyle** | Move under Research; adopt the card system and terminology. |
| The Wire | **Keep, simplify** | Becomes News & Context; also feeds context chips on cards. |
| BA paradox, bankroll backtest | **Keep, relocate** | Education center and Track Record (historical section). |
| Team Pricer with Front Office sliders | **Simplify** | Becomes "Team strength" with a "what-if" panel inside Research → Teams & Season. |
| Edge Finder (manual price, any two teams) | **Simplify** | Becomes the "Check a price" tool inside game detail and the Matchups page. |
| Desk tab as default | **Redesign** | Replaced by Today. |
| Navigation (six terminal tabs) | **Redesign** | Five primary destinations plus a Research hub (section 4). |
| Verdict presentation (VALUE / NO VALUE in huge type) | **Redesign** | Verdict pill with sentence-case label, icon, and one-line takeaway. |
| Parlay Lab | **Redesign** | Verdict-first Parlay Check with singles comparison. |
| Bankroll (paper $1,000 backtest only) | **Redesign** | Real user bankroll, profiles, stakes, limits. |
| Terminology, labels, uppercase mono everywhere | **Redesign** | Terminology dictionary; monospace reserved for prices. |
| Visual system (terminal dark, saturated green/red) | **Redesign** | Token-based, two themes, desaturated semantics. |
| Terminal boot sequence | **Retire** | Replace with a plain skeleton. Keep as an optional easter egg if the team is attached to it. |
| Blinking LIVE dot, uppercase status strip | **Retire** | Replace with a quiet data-status row with timestamps. |
| Model slip of the day | **Retire from default surfaces** | See above. |
| "STATISTICAL RESEARCH · NOT WAGERING ADVICE" tag | **Keep, restyle** | Sentence case: "Research tool, not betting advice. 21+." Present on every screen. |

---
## 4. Recommended information architecture

### 4.1 Organizing principles

The current tab row (Desk, Players, H2H, Parlay, Season, Wire) is organized by *tool*. The redesign organizes by *frequency and intent*: things a person does daily sit in the primary navigation; things a person does when researching sit one level down in a hub; money sits in one place; and trust has its own destination. Four rules follow.

Daily surfaces come first and answer questions; research surfaces come second and enable exploration. Everything about the user's money — bankroll, stakes, logged bets, limits — lives in one area so the product never nudges from a research screen. The model's own record is a primary destination, not a panel. And every screen carries the same honesty furniture (disclaimer, data status, sample labels) so no route feels like a different product.

### 4.2 Site map

```
Today (default)
├── Game detail  /game/{gamePk}
│   ├── Verdict · Price comparison · Why · Context · Risk · Stake · Numbers
│   └── Check a price (manual entry, any book)
Research (hub)
├── Players            player cards, percentiles, run value, what-would-Beane-buy
├── Matchups           team vs team (live or historical seasons), player vs player
├── Teams & Season     team strength + what-if, projected standings, remaining schedule, screener
├── News & Context     transactions, injuries, headlines, desk notes, pulse evidence
└── Learn              education center, glossary, how the model works, BA paradox, model changelog
Parlay Check
Track Record
├── Live paper record (all leans · candidates only · parlays)
├── By segment (season vs starter-adjusted, favorites vs underdogs, signal strength, edge size)
├── Calibration (live) · Closing-line value
├── Historical backtests (2002–2012, clearly separated)
└── Methodology · Model changelog
Bankroll
├── Setup and risk profile
├── Stake calculator
├── My bets (log, grading, closing-line value, export)
└── Limits, cooling-off, resources
Settings / Account
    detail level · explain terms · theme · my sportsbooks · time zone · notifications · subscription
```

### 4.3 Evaluation of the proposed navigation

| Proposed label | Recommendation | Why |
|---|---|---|
| Today | **Primary, default** | The product's front door. |
| Find an Edge | **Do not ship as a destination** | Today filtered to candidates is the same thing; the name promises a daily edge the doctrine forbids claiming. The manual price tool survives as "Check a price" in game detail and as Matchups in Research. |
| Players | **Secondary, under Research** | Weekly research, not a daily task; the probable starters on each card deep-link into it, so it stays one tap away. |
| Matchups | **Secondary, under Research** | Same. |
| Parlay Builder | **Primary, renamed Parlay Check** | It earns a primary slot because it is the product's most teachable moment, but "Builder" implies constructing bets and "Check" implies evaluating them. |
| Team & Season Trends | **Secondary, renamed Teams & Season** | "Trends" invites streak content the model does not use. |
| News & Context | **Secondary, under Research** | Context is important but not a daily destination; it also flows into cards as chips. |
| Track Record | **Primary** | Trust is a feature. |
| (not proposed) Bankroll | **Primary** | The bankroll-first strategy needs a home that is not a settings page. |

Five primary destinations fit a phone's bottom bar and a desktop's top bar without truncation: **Today · Research · Parlay Check · Track Record · Bankroll**. Research opens a hub screen with five tiles on mobile and a dropdown on desktop. Search (the existing omnisearch across teams, players, and seasons) stays global, with "/" as the shortcut; number keys 1–5 switch primary destinations for keyboard users.

Shareable, stateful URLs remain a requirement everywhere (`/game/{gamePk}`, `/research/matchups?a=NYY-2026&b=BOS-2026`, `/record?segment=candidates`), which also makes support and QA tractable.

### 4.4 Cross-links that make the architecture feel like one product

A probable starter's name on a card opens his player card. A team name opens Team strength. An injury chip opens the relevant News & Context item. "See how candidates have performed" on a card opens the Track Record filtered to that verdict. "Log this bet" on a stake card opens Bankroll → My bets with the game and price pre-filled. Every tooltip has a "Learn more" that opens the matching Learn article. None of these links leave the app or point at a sportsbook.

| | |
|---|---|
| User problem | Users cannot tell which of six tool-named tabs answers a daily question; money and research are mixed. |
| Why it helps | Frequency-based navigation puts the daily answer first, fits mobile, and separates research from action. |
| Advanced data preserved | Every existing panel keeps a home under Research or Track Record; nothing is removed. |
| Trust effect | Track Record and Bankroll as primary destinations signal that the product is about honesty and discipline. |
| Effort | Low to Medium — routing and layout work; existing panels are moved and restyled, not rebuilt. |

---

## 5. Today dashboard concept

### 5.1 The page's job

Today answers one question in five seconds — *which games deserve my attention?* — and makes "none of them" a satisfying answer. It is a list of research cards grouped by verdict, with a summary strip at the top that states the day's pass rate. It never looks like a betting slip.

### 5.2 Layout

**Desktop.** A single content column of cards (about 720–780 px wide, for reading comfort) with a right rail. The rail holds the daily summary, the bankroll widget when a bankroll is set, a small Track Record snapshot with its sample size, and a short context feed of today's relevant injuries and transactions. Under roughly 1,100 px the rail collapses into a summary strip above the cards.

**Mobile.** One column. The summary strip is sticky under the date bar; the bankroll widget becomes a one-line chip; the context feed moves into each card's context layer.

Top to bottom:

1. **Date bar.** Yesterday · Today · Tomorrow, with the date. Tomorrow shows season prices and "starters not yet confirmed" states; Yesterday shows graded results.
2. **Data status line.** "Team stats through 126 games · Prices as of 6:42 PM ET from DraftKings and FanDuel · Model v2.3." One sentence, always visible, muted.
3. **Summary strip.** "15 games · 2 bet candidates · 1 marginal · 9 no value detected · 3 waiting on data." Tapping a count filters the list.
4. **Filter and sort bar.** Filters: All · Candidates only. Sort: By verdict (default) · By start time · By edge. Price source: My books · Best available.
5. **Sections of cards.** *Worth a look* (candidates and marginal), *No value detected*, *Waiting on data*, *In progress and final*. Section headers carry a one-line explanation the first time they appear ("The model passes on most games; a quiet day is normal").
6. **Footer.** "Research tool, not betting advice. 21+. Problem gambling help: 1-800-GAMBLER." Model version and data sources repeat here in full.

### 5.3 Ordering rules

Within *Worth a look*, cards sort by expected return descending, then by start time. Everything else sorts by start time. Games in progress move to the bottom section with a live score and the model's pre-game price frozen; final games show the score and the graded result for both prices. A user who prefers a pure schedule view switches to "By start time" and the choice persists.

### 5.4 Designed states

| State | What the user sees |
|---|---|
| No candidates today | The summary strip reads "0 bet candidates," and the *Worth a look* section shows a short, calm message: "Nothing stands out at today's prices. The model passes on most games — passing costs nothing." |
| Odds feed unavailable | Cards show the lean, model chance, and fair price; the price row reads "No price loaded — add one to check value," with the manual entry inline. Verdicts read *Insufficient data (no price)*. The status line says when prices were last available. |
| Prices stale (older than 15 minutes) | An amber "As of 5:10 PM" chip on the price row; the verdict keeps its label but the card gains a "price may have moved" note. |
| Starters not confirmed | Only the season price is shown; the starter-adjusted price reads "waiting on starters." Signal strength is capped at *Moderate* because one of the two prices is missing. |
| Small sample (early season) | A "Through 18 games — small sample" chip; below a published threshold (30 games), verdicts are withheld and the card reads *Insufficient data (early season)* with the model chance still visible and labeled. |
| Off-season | Today becomes a historical mode: a note that the season is over, the final Track Record for the year, and the education center's featured lessons. Never an empty page. |
| Game postponed or in progress | The card transforms to a status card; no verdict is shown for an in-progress game. |

### 5.5 What Today deliberately does not include

No "bet now" or sportsbook links. No countdown timers, streak badges, hot-hand callouts, or "trending picks." No social proof ("78% of users like Boston"), because it encourages herding and has nothing to do with the model. No flashing or color-shifting numbers when prices move. No auto-generated urgency copy. The most excited the page is allowed to get is a verdict pill that says *Bet candidate*.

| | |
|---|---|
| User problem | The Desk shows one team-season pipeline by default and a rail of prices; nothing tells a newcomer which games matter or that most games are a pass. |
| Why it helps | Answer-first cards grouped by verdict turn a scan into a decision in seconds; the summary strip makes "pass" a visible, normal outcome. |
| Advanced data preserved | Every card expands to the full receipts; season and starter-adjusted prices, sample sizes, and context chips remain visible. |
| Trust effect | Verdict grouping plus the pass rate is the strongest possible signal that this is research, not a pick sheet. Stale and missing-data states are explicit. |
| Effort | Medium for the page; High overall because it depends on the odds feed and the verdict engine (Appendix A). |

---
## 6. Game-card UX

### 6.1 Is the proposed hierarchy right?

Partly. The proposed card (teams, time, model lean, model chance, fair price, book price, edge, confidence, risk, explanation, button) contains the right ingredients in roughly the wrong order, and it treats every game with the same density, which recreates the terminal problem in card form. Five corrections:

The **verdict leads, not the lean.** A lean exists for every game; a verdict is the answer to "should I consider this?" Leading with the lean produces the wrong instruction whenever the value side is the underdog, which is often.

**Book price sits next to model chance, with fair price as the comparison**, because the price the reader can actually get is the fact, and the fair price is the yardstick. The proposed order (fair before book) reads like the model is the fact and the market the footnote.

**"Confidence" becomes signal strength**, defined on the card, and the risk row states the chance the bet loses.

**Explanation splits into two labeled parts**: why the model leans the side (priced inputs) and why the bet is a candidate (the price), followed by context the model does not price.

**Cards have three layers** — answer, explanation, numbers — and the detail-level preference decides how many are open by default. A collapsed card is four lines; a fully open card is the entire Edge Finder.

### 6.2 The card, layer by layer

**Layer 1 — the answer (always visible).**

Identity row: away at home, start time in the user's time zone, probable starters (each tappable). Verdict pill with an icon and a one-line takeaway written by the explanation generator. The comparison line: model chance, book price with the book named, fair price. The edge line: edge in points and expected return per $100. A chip row: signal strength, "loses X% of the time," and the sample label.

**Layer 2 — the explanation (open by default in Full detail; one tap in Essentials).**

"Why the model leans Boston" — up to three bullets generated from the receipts, each with a number. "Why it's a candidate" — one sentence about the price. "Context, not in the price" — chips for injuries, transactions, media pulse, and standing limitations ("the model does not price home-field advantage, weather, or lineups"). Risk detail — chance of losing, payout shape, break-even win rate, model uncertainty. The stake card, if a bankroll is set.

**Layer 3 — the numbers ("Show the numbers").**

A two-side table: model chance, fair price, each book's price, implied chance, edge, expected return, break-even. Season price and starter-adjusted price with the blend weight. Receipts: the inputs (OBP, SLG, OBP-against, SLG-against, the starter's OBP-against and SLG-against), predicted runs scored and allowed, Pythagorean strength, and the log5 result. Line movement from open to now. The Kelly arithmetic (full, fractional, shrinkage, cap). Links to the Track Record filtered to this verdict and signal bucket, to Team strength, and to Matchups.

The "See full breakdown" action opens the game detail page: the same three layers at full width, plus the "Check a price" tool for entering any book's line.

### 6.3 Three example cards

The odds arithmetic below uses the app's own conversions (probability to American odds rounded to the nearest 5; implied chance from the American line; expected return per $100 = 100 × [p × (decimal odds − 1) − (1 − p)]) and is exact. The team statistics, starters, and prices are illustrative placeholders, not live data.

**A bet candidate**

```
NYY at BOS · Tonight 7:10 PM ET · Rodón (NYY) vs Crochet (BOS)

●  Bet candidate — Red Sox
   The book's price on Boston is better than the model's fair price.

   Model chance 58%      Book −115 (DraftKings)      Fair −140
   Edge +4.5 pts  ·  Expected return +$8 per $100

   Signal: Strong   ·   Loses 42% of the time   ·   Through 126 games

   ▸ Why the model leans Boston    ▸ Context    ▸ Numbers
                                              [ See full breakdown ]
```

Expanded explanation for this card:

```
Why the model leans Boston
  • Boston's offense projects to more runs: 4.9 per game vs 4.3
    (on-base .340 vs .318, slugging .431 vs .402).
  • Boston's run prevention is stronger: 4.1 allowed vs 4.6.
  • Tonight's starter helps Boston: Crochet holds hitters to a .270
    on-base average, better than Boston's team rate. With starters,
    the price moves from −135 to −140.

Why it's a candidate
  • DraftKings has Boston at −115. The model's fair price is −140,
    so the book is offering better odds than the model thinks the
    matchup deserves.

Context — not in the price
  ⚑ Yankees: Judge (60-day IL)   ·   Home field: not priced by the model
  Media pulse: NYY −41 (12 items)   ·   Lineups: not priced

Risk
  Loses 42% of the time. Risk $115 to win $100. You need to win 53.5%
  of bets like this to break even at −115; the model says 58%.
  Model uncertainty: moderate — season-level inputs, starters confirmed.
```

**No value detected**

```
LAD at SD · 9:40 PM ET · Glasnow (LAD) vs Cease (SD)

○  No value detected
   The model leans the Dodgers (55%), but the book has them at −150,
   which implies 60%. The Padres at +125 are inside the book's cut.

   Model chance 55%      Book −150 (FanDuel)      Fair −120
   Edge −5 pts on LAD  ·  +0.6 pts on SD (inside the cut)

   Signal: —   ·   Through 127 games

   ▸ Why the model leans Los Angeles    ▸ Context    ▸ Numbers
```

**Insufficient data**

```
SEA at TEX · 8:05 PM ET · Starters not announced

◌  Waiting on data
   Season strength leans Seattle (53%). No price is loaded yet and
   starters are not confirmed; the verdict appears when both exist.

   Model chance 53% (season)      Book —      Fair −115

   [ Add a price ]    ▸ Why    ▸ Context
```

### 6.4 The card contract

These rules hold in every mode, on every device, and in every future feature that renders a game.

1. The verdict is computed for both sides and names the value side. If the value side differs from the lean, the takeaway says so in one sentence.
2. Edge and expected return never appear without a price, a book name, and a timestamp.
3. A stake never appears without a bankroll, a risk profile, and positive expected return.
4. Bullets under "Why the model leans" come only from priced inputs; everything else is labeled "not in the price."
5. Sample label, staleness stamp, and the research disclaimer are never collapsible.
6. Essentials and Full detail show the same verdict; Full detail adds information and never changes it.
7. Color is never the only signal; every verdict has an icon and a word.
8. No sportsbook links, no urgency copy, no countdowns.
9. When a game goes live, the pre-game price and verdict are frozen for grading and the card stops showing a verdict.
10. Every number has a definition one tap away, and every calculation has a "how this is calculated" expander that plugs in the actual figures.

### 6.5 Signal strength, defined

Signal strength answers "how far is the model from the market, relative to how wrong the model usually is?" It is computed from three ingredients: the edge in points divided by the model's typical probability error (a published constant, initially set from the backtest and revised from live calibration, on the order of 4 points); agreement between the season and starter-adjusted prices (both must show positive expected return on the same side); and data completeness (starters confirmed, sample at or above 60 games, price fresh).

*Strong* requires a gap ratio of at least 1.0, agreement, and complete data. *Moderate* requires a gap ratio of at least 0.5, or a strong gap with one ingredient missing. Everything else is *Weak*. The label carries a permanent tooltip: "Signal measures disagreement with the market, not certainty. Strong signals still lose often." The Track Record reports results by signal level, and each level's label is marked *provisional* until at least 200 graded candidates exist in that bucket. If a level stops outperforming the others, the product says so on the record page rather than quietly redefining the level.

### 6.6 The risk row, defined

The single most honest risk statement is "loses X% of the time," computed as one minus the model chance; it appears on every card with a verdict. The full risk detail adds the payout shape ("risk $115 to win $100"; volatility tag *Lower* for favorites at −200 or shorter, *Higher* for underdogs at +150 or longer, *Typical* otherwise), the break-even win rate at the offered price, and model uncertainty (*Low*, *Moderate*, or *High* from sample size and the gap between the two prices). The product does not compress these into a single risk score; a single score would be false precision.

| | |
|---|---|
| User problem | A newcomer cannot tell from the current SlateRail row whether a game is worth anything, why, or what it risks; an expert cannot see it at a glance either. |
| Why it helps | Verdict-first, three-layer cards answer the seven questions in order; the collapsed state is readable in two seconds and the expanded state is the whole Edge Finder. |
| Advanced data preserved | Layer 3 holds every existing number: both prices, receipts, inputs, line movement, Kelly arithmetic. |
| Trust effect | Naming the value side (not the lean), showing the chance of losing, separating priced from context, and freezing the pre-game verdict for grading all make the card auditable. |
| Effort | Medium for the component; the explanation generator (Appendix B) and signal-strength logic add a further Medium. |

---

## 7. Beginner and Advanced modes

### 7.1 Recommendation: progressive disclosure, one preference, one toggle

Do not build Beginner and Advanced as modes. Build every component with three layers (answer, explanation, numbers) and let two independent settings govern defaults:

**Detail level** — *Essentials* or *Full detail*. It controls how many layers open by default, whether chips show technical secondary labels, and whether tables render (Full detail) or key-value rows render (Essentials). It never changes a verdict, a number, or a threshold.

**Explain terms** — on or off. It controls inline definitions, first-encounter coach marks, and the "how this is calculated" prompts. It is independent of detail level because newcomers who want the full numbers still want explanations, and experts who want density do not.

The first-run default is Essentials with explanations on. A quick toggle for detail level sits in the Today header so the choice is discoverable, and the app makes one quiet suggestion after a user has opened "Show the numbers" on ten cards: "You open the numbers often — switch to Full detail by default?"

### 7.2 What each level shows by default

| Surface | Essentials | Full detail |
|---|---|---|
| Today card | Layer 1 only; chips without technical labels | Layers 1 and 2 open; chips carry technical labels ("Edge (model − implied)") |
| Game detail | Layers 1 and 2; numbers behind one tap | All three layers open; two-side table; line movement; Kelly arithmetic |
| Track Record | Headline record, units, ROI with interval, sample, CLV; charts simplified | Segment tables, calibration buckets with counts, per-pick table, exports |
| Parlay Check | Verdict, combined chance, fair vs book, house cut, singles comparison | Per-leg table, EV arithmetic, correlation notes, Kelly |
| Bankroll | Bankroll, profile, unit, stake in dollars, limits | Kelly fraction, shrinkage weight, cap, drawdown simulation |
| Research | Cards and percentile bars with plain labels | Raw stat tables, regression inputs, receipts, CSV export |

### 7.3 Why not per-page settings, and why not modes

Per-page toggles produce inconsistent state: a user leaves Today in Essentials, lands on Track Record in Full detail, and the product feels like two products. Global modes labeled Beginner and Advanced produce a self-selection problem (nobody picks Beginner twice) and a maintenance problem (every screenshot, support article, and test exists twice). Progressive disclosure inside each component keeps one implementation, one verdict, and one vocabulary, and lets a person go deeper on one card without changing anything else.

The one thing a mode system would offer that this does not is hiding the honesty furniture in the simple view. That is not a feature. Sample labels, staleness stamps, and the research disclaimer render in both levels.

| | |
|---|---|
| User problem | Newcomers are overwhelmed by density; experts are slowed by explanation; a mode switch makes the product feel unstable. |
| Why it helps | Layers keep the answer readable and the depth available; the two settings match how people actually differ (how much, and whether to explain). |
| Advanced data preserved | Everything, one tap away in Essentials and open by default in Full detail. |
| Trust effect | The same verdict in both levels prevents the suspicion that simple view hides bad news. |
| Effort | Low to Medium — a preference store, a disclosure component, and a rule that every component declares its layers. |

---

## 8. Plain-English terminology

### 8.1 The approach: dual labels, one dictionary, calculations that show their work

Every metric is labeled three ways, and one source of truth in code produces all three: a plain-English primary label, a technical secondary label (shown in Full detail and in tooltips), and a one-sentence tooltip with a "Learn more" link into the education center. Wherever a number is the result of arithmetic, a "How this is calculated" expander shows the formula *with the user's actual numbers substituted* — "Edge = 58% model chance − 53.5% implied by −115 = +4.5 points" — because a formula with real numbers is an explanation and a formula with symbols is a textbook.

The dictionary lives in code (`terminology.ts` or equivalent) and is consumed by components, tooltips, coach marks, glossary, and documentation, so a term is never defined two different ways in two places. Renaming a metric is a one-line change.

Tooltips are for definitions, expanders are for arithmetic, coach marks are for first encounters, and the education center is for concepts that need more than a sentence (why high-probability bets lose, why parlays are expensive, what the model does not know). Nothing is explained only in onboarding.

### 8.2 The dictionary

| Metric | Plain label (primary) | Technical label (secondary) | Tooltip |
|---|---|---|---|
| Model probability | Model chance | Model probability | The model's estimate of how often this side wins the matchup. |
| Fair odds | Fair price | Fair odds (no vig) | The price at which this bet would break even if the model's chance is right. |
| Implied probability | Price says | Implied probability | The win rate the sportsbook's price assumes, including its cut. |
| Edge (pp) | Edge | Model chance − implied chance | How much likelier the model thinks this side is than the price implies, in points. |
| Expected value | Expected return per $100 | EV per unit | What a bet like this makes or loses on average over many bets. Not what happens on any one bet. |
| Vig | Sportsbook's cut | Vig / hold | The fee built into the prices; both sides' implied chances add to more than 100%. |
| Break-even rate | Win rate needed to break even | Break-even probability | How often you must win at this price to neither gain nor lose. |
| Kelly stake | Model-sized stake | Fractional Kelly | A stake sized to the edge and the odds, scaled down for uncertainty and capped by your profile. |
| Units | Units | — | One unit is your standard stake; records are kept in units so bettors with different bankrolls can compare. |
| ROI | Return on money risked | ROI | Profit divided by the total amount staked. |
| Closing-line value | Beat the closing price | CLV | Whether the price you got was better than the final price before first pitch. Consistently beating the close is the best early sign of an edge. |
| Season price | Season strength price | Season-input log5 price | The price from each team's season-to-date hitting and run prevention. |
| Starter-adjusted price | With tonight's starters | Starter-blended price | The season price with the probable starter's rates blended into run prevention. |
| Signal strength | Signal | Gap ratio | How far the model is from the market relative to its usual error. Disagreement, not certainty. |
| Calibration | When the model says 60%, how often it happens | Calibration | Whether the model's chances match real outcomes over many games. |
| Sample size | Games in this estimate | n / games played | How much data the estimate rests on. Small samples swing. |
| Percentile | Rank among qualified players | Percentile | Where a player stands versus everyone with enough playing time this season. |
| mWAA | Wins added vs an average player (model) | Model wins above average | Runs the player adds or prevents versus average, converted to wins. Offense or pitching only. |
| Pythagorean / log5 | How runs become a win chance | Pythagorean + log5 | Predicted runs give each team a strength; the two strengths give the matchup chance. |
| Correlation (parlay) | Legs that move together | Correlated legs | When one leg winning makes another likelier, multiplying chances overstates the parlay's odds. |
| Variance | Swings | Variance / drawdown | How far results wander from the average on the way there. |

### 8.3 Number formatting rules

Model chance shows whole percentages in Essentials (58%) and one decimal in Full detail (58.2%). American odds always carry a sign and are set in the monospace price face (−115, +140). Edge is in points ("+4.5 pts"), never a percent sign, to keep it distinct from expected return. Expected return is in dollars per $100 in Essentials ("+$8 per $100") and as a percent of stake in Full detail ("+8.4%"). Records are "wins–losses" with units to one decimal ("41–37, +2.1 units"). Every table with numbers uses tabular numerals and right alignment.

### 8.4 Language rules

Allowed verdict language: bet candidate, marginal value, no value detected, avoid at this price, insufficient data, model lean, potential edge, signal, provisional. Allowed uncertainty language: loses X% of the time, small sample, as of, waiting on, not in the price, provisional, the record decides. Prohibited anywhere in product, notifications, marketing, or share cards: lock, guaranteed, free money, can't lose, sure thing, hot, on fire, streak, must-bet, best bet, play of the day, fade, boost, risk-free, bet now. The full copy rulebook is Appendix D and is enforced by a lint on string resources.

| | |
|---|---|
| User problem | Labels like EDGE, EV, VIG, and ½-KELLY are meaningless to the primary persona and the current UI never explains them. |
| Why it helps | Dual labels let both personas read the same screen; arithmetic with real numbers substituted teaches faster than any tutorial. |
| Advanced data preserved | Technical labels remain visible in Full detail and in every tooltip; no metric is renamed away. |
| Trust effect | Showing the formula with the actual figures is the strongest possible "nothing hidden" signal. |
| Effort | Low — a dictionary, a tooltip component, an expander component, and a copy lint. |

---
## 9. Parlay Builder redesign — "Parlay Check"

### 9.1 Reframe: a checker, not a builder

The existing Parlay Lab has the right mathematics and the right honesty. What changes is the frame and the order of information. A builder's job is to help you assemble a bet; a checker's job is to tell you whether the bet you are about to make is any good. The page is renamed **Parlay Check**, its verdict comes first, and its most important output is the comparison with the same legs bet singly. The page should be comfortable saying, in plain words, "this parlay is poor value," and it should say so more often than not, because that is usually true.

### 9.2 The flow

A user adds legs from Today (a "Add to parlay check" action inside each card's numbers layer, so it is never the card's primary call to action) or from the Parlay Check page's own game list. Each leg shows the side, the model chance, and the book price. Legs from the same game are refused with a one-line explanation, exactly as today. Up to six legs.

The page then shows, in this order:

1. **Verdict pill and takeaway.** *Poor value*, *Marginal*, or *Candidate*, with one sentence: "This parlay pays +365; the model's fair price is +415. You are giving up about 9.5 cents per dollar."
2. **The three numbers.** Model chance the whole slip wins; fair parlay odds; the book's parlay odds (entered, or computed from the legs' prices when the book compounds them — the app states which).
3. **The house-cut comparison.** A bar showing the book's cut on this parlay versus the average cut on the same legs as singles. For coin-flip legs at −110 this is the vig-compounding strip in a new outfit: 4.5% for one leg, 8.9% for two, 13.0% for three, 17.0% for four, 20.8% for five.
4. **Singles instead.** Each leg's expected return per $100 on its own, and the parlay's expected return per $100, side by side, with a sentence: "Betting Boston alone has a higher expected return and wins 58% of the time; this parlay wins 14% of the time."
5. **Expected return and risk.** Expected return per $100; chance the slip loses (one minus the combined chance); "what you need": the win rate the payout requires versus the model's.
6. **Correlation notes.** Same-game legs are refused; legs that share a weather system, a doubleheader, or a common starter change are flagged with a note that the independence assumption may overstate the combined chance.
7. **Stake.** Only if expected return is positive and a bankroll is set; parlay stakes use the profile's parlay cap, which is half the singles cap.
8. **The numbers.** Per-leg table (model chance, implied, edge, expected return), the multiplication, the decimal-odds conversion, Kelly arithmetic.

### 9.3 Two worked slips

**A typical recreational slip — three favorites.** Legs at −150, −160, and −140 where the model's chances are 58%, 60%, and 56%. Each leg is slightly negative on its own (−3.3%, −2.5%, and −4.0% per $100). The book pays +365; the model's fair price is +415; the slip wins 19.5% of the time and its expected return is **−$9.50 per $100** — roughly three times worse per dollar than the average single. Verdict: *Poor value*. Takeaway: "Each of these prices is a little worse than fair; multiplying them makes it much worse."

**A slip with a real candidate in it.** Boston −115 (model 58%), San Diego +125 (model 45%), Chicago −130 (model 55%). Boston alone returns +$8.40 per $100; San Diego +$1.25; Chicago −$2.70. The parlay pays +645 against a fair +595, so its expected return is +$6.80 per $100 — but it wins 14% of the time, and it returns *less* per dollar than betting Boston alone. Verdict: *Marginal*. Takeaway: "Boston is the value here. Adding two ordinary legs lowers the expected return and makes the outcome far more of a coin toss." This is the slip that teaches the lesson your brief asks for: individual bets may be better than the parlay, and the product says so unprompted.

### 9.4 What stays and what goes

The independence assumption stays, stated out loud on the page. The refusal of same-game legs stays. The parlay line in the Live Record stays and gains prominence: "Parlays logged by the model: 3–9, −4.2 units" is the most persuasive parlay education the product owns. The "model slip of the day" leaves the default view; if the parlay record ever shows a combination type that holds up, the feature can return as an example inside the education content, never as a daily featured pick.

| | |
|---|---|
| User problem | Parlays are the primary persona's favorite bet and the worst-priced one; nothing in their sportsbook tells them so. |
| Why it helps | Verdict-first and singles-first make the comparison unavoidable in one glance; the house-cut bar makes compounding visible. |
| Advanced data preserved | Full per-leg table, the multiplication, decimal conversions, EV and Kelly arithmetic, correlation notes. |
| Trust effect | A product that confidently rates most parlays "poor value" is behaving against its own short-term engagement interest, which readers notice. |
| Effort | Low to Medium — existing math, new layout and copy. |

---

## 10. Bankroll and responsible-use experience

### 10.1 Bankroll-first, with the arithmetic shown

Users set a bankroll once ("money set aside for betting that you can afford to lose") and a risk profile. From then on every candidate shows a dollar-sized *model stake* with its share of bankroll, and every stake explains itself. Users who never set a bankroll never see a dollar figure; they see the Kelly fraction as a percentage in Full detail only.

### 10.2 Risk profiles

| Profile | Kelly fraction | Cap per single | Cap per parlay | Plain description |
|---|---|---|---|---|
| Conservative | ¼ Kelly | 1% of bankroll | 0.5% | Small stakes, small swings. Losing streaks barely dent the bankroll. |
| Balanced (default) | ½ Kelly | 2% of bankroll | 1% | The usual compromise between growth and swings. |
| Higher variance | ¾ Kelly | 3% of bankroll | 1.5% | Larger stakes and noticeably larger drawdowns. Not recommended for new bettors. |

"Aggressive" is not offered. The third profile is named for what it does, its description states the cost, and it is not selectable during onboarding — only from the Bankroll page after reading its drawdown description.

### 10.3 Sizing on a shrunk edge

The model's edge is an estimate from a season-level model whose game-level edge is unproven. Sizing on the raw model chance would produce stakes that are far too large: on the example card (model 58%, price −115) full Kelly is 9.7% of bankroll, and even half Kelly is 4.9%. The product therefore sizes stakes on a **staking chance** that blends the model's chance with the market's de-vigged chance, initially at equal weight. The weight on the model is a published constant that can only move toward the model when the live record justifies it — the same "advice must be earned" rule, applied to stake sizing.

On the example card the market's de-vigged chance for Boston is 52.3% (from −115/+105), the staking chance is 55.2%, full Kelly is 3.6% of bankroll, and the profiles produce $9 (Conservative), $18 (Balanced), and $27 (Higher variance) on a $1,000 bankroll. Every stake card shows the whole chain in Full detail: model chance, market chance, staking chance, full Kelly, fraction, cap, rounding. The "Balanced" default and the shrinkage together mean the product's largest ordinary stake is 2% of bankroll — a number a person can live with through a bad month.

### 10.4 Stake card anatomy

```
Model-sized stake (paper)                         Balanced · $1,000 bankroll
$18   ·  1.8% of bankroll
If it loses: bankroll → $982.   If it wins: → $1,016.
Over 100 similar bets, sized like this: about +$57 on average;
roughly 1 in 3 such stretches ends down. Typical worst dip: 15%.
Projected on the staking chance (55%), not the model's 58%.
▸ How this is sized     [ Log this bet ]     [ Not betting this ]
```

The expectation and the variance line come from a quick simulation using the staking chance rather than the model's chance, so the projection is as conservative as the sizing. They exist so that the honest statement "you can do everything right and still be down after 100 bets" is on the stake itself, not buried in a lesson. "Log this bet" opens My bets with the game, side, price, and stake pre-filled; the stake stays labeled *paper* until the user confirms a real bet.

### 10.5 My bets

A log of the user's own bets — from the stake card, or entered manually for bets placed on anything, including games the model passed on. Each entry records the price taken; the app captures the closing price for that market and grades the bet when the game is final. The page reports record, units, return on money risked with an interval, and average closing-line value, and it compares the user's results to the model's over the same games. The comparison is presented gently: "On the 42 games you and the model both bet, you took a better price 19 times." It is the secondary persona's spreadsheet and the primary persona's mirror.

### 10.6 Responsible-use toolkit

These are part of the Bankroll feature, not a settings page, and they are shown during bankroll setup.

Limits: a weekly loss limit and an optional daily session-count reminder, set by the user, with a notice when reached and stakes hidden until the period rolls over. Cooling-off: a switch that hides all stakes and dollar figures for 24 hours, 7 days, or 30 days, with no confirmation friction to turn on and a delay to turn off. Paper mode: the default state; a user can keep the entire product in paper mode indefinitely. Resources: the National Council on Problem Gambling helpline (1-800-GAMBLER) and a short, non-judgmental self-check, both one tap from the Bankroll page and in the footer of every screen. Notifications: never about a stake, a price move, or a candidate; informational only, and off by default (section 15).

Language rules for money: the product says "model-sized stake," never "recommended bet" or "suggested bet"; "paper" until confirmed; "no stake — no value at this price" when expected return is not positive; and never shows a dollar figure on a share card or in a notification.

| | |
|---|---|
| User problem | Bettors size by feel; Kelly is meaningless as a percentage; a $10 unit and a $100 unit are different products. |
| Why it helps | Dollar stakes tied to a bankroll and a profile turn abstract sizing into a practical, bounded number with its consequences shown. |
| Advanced data preserved | Full Kelly, fraction, shrinkage weight, cap, and the variance simulation are all visible in Full detail. |
| Trust effect | Shrinkage and caps demonstrate that the product does not believe its own edge more than the record justifies; limits and cooling-off show the product's incentives are aligned with the user's. |
| Effort | Medium for sizing, the stake card, and setup; Medium to High for My bets with closing-line capture (depends on the odds feed and accounts). |

---
## 11. Trust, transparency, and track record

### 11.1 Four records, four treatments

The brief asks the product to distinguish backtested results, live paper picks, user-entered bets, and graded completed picks. They should never share a number, a chart, or a color.

| Record | What it is | Treatment | Never |
|---|---|---|---|
| Historical tests | The chronological backtest (trained through 2001, tested 2002–2012): R² 0.88 on unseen seasons, wins within ±3.25 on average, playoff calls right 89.4% versus a 72.7% majority baseline, calibration buckets, the paper bankroll backtest | Its own section with a persistent banner: "Historical, season-level, 2002–2012. Not bettable. Shown so you can judge the model's foundations." Muted, hatched chart fills. | Combined with live results; quoted as a betting record |
| Live paper record | Every day's frozen snapshot of the model's prices and picks, graded against real final scores; season and starter-adjusted graded side by side; candidates graded at the price shown; parlays graded all-or-nothing | The page's hero. Solid chart fills. Always with "since" date, sample size, and interval. | Edited, reset, or filtered to hide losses |
| My bets | The user's own logged bets, graded, with closing-line value | Private, personal accent color, on the Bankroll page, with a comparison to the model over the same games | Mixed into the public record |
| Graded vs pending | Status of each pick | Pending picks are outlined and excluded from totals; graded picks are solid | Counted before grading |

### 11.2 The Track Record page

**Hero — the live record.** "Tracking since August 2026 · 412 picks · 398 graded." Record, units, return on money risked with a 95% interval, and average closing-line value once prices exist. Beneath it, one paragraph titled "What this proves" (11.3).

**Three records side by side.** *All leans* (every game, one flat unit on the side priced above 50%), *Candidates only* (verdict-engine candidates at the price shown when the verdict was issued), and *Parlays* (logged slips). The candidates record is the one a paying customer cares about and the one the product must be most careful with; it exists only from the date the odds feed went live, and says so.

**The experiment.** Season price versus starter-adjusted price, graded on the same games, with the line "The record decides which price is better; the product does not." When one has a meaningfully better record over a stated minimum sample, the page says so; until then it says "too early to tell."

**By segment.** Favorites versus underdogs, signal strength (Strong, Moderate, Weak), edge size buckets, and by month, each with sample size and interval; any bucket under 50 graded picks carries a "too small to read" note. This is where the signal-strength label earns or loses its meaning.

**Calibration, live.** When the model said 55–60%, how often did that side win, with counts per bucket. The backtest calibration lives in the historical section, not here.

**Closing-line value.** The share of picks that beat the closing price, the average CLV in points, and a short explanation of why CLV shows an edge sooner than wins and losses do.

**Historical tests.** The existing Track Record and bankroll backtest panels, restyled, under the banner above.

**Methodology and changelog.** How the model works in five paragraphs with links to the receipts; the verdict-engine rules with their current thresholds; every model change with its date and its record since that date.

**How many bets it takes.** A small explainer with the arithmetic: at a 5% return, about 1,600 bets are needed before the result is reasonably distinguishable from luck; at 3%, about 4,400. With the current sample, the widest swing that luck alone could produce is shown in units.

### 11.3 "What this proves" — the standing copy

> This record shows how the model's paper picks have done against real final scores at the prices shown at the time. It is graded every day and never edited. It does not prove the model will keep winning, and it does not prove the model has an edge: over 398 picks, luck alone can move the result by about ±20 units. The historical tests below show the model's foundations on past seasons; they are season-level and cannot be bet. If you want an early sign of whether the model's prices are sharp, look at closing-line value, which shows up in hundreds of bets rather than thousands.

### 11.4 Public by default

The logged-out home page is the Track Record snapshot and today's summary strip. Someone deciding whether to trust the product should meet its losses before its features. This is also the page marketing links to, and marketing quotes it only with the qualifiers it carries.

### 11.5 Trust mechanics beyond the record

A **data status page** shows every source, its last successful fetch, its cache age, and its current state; the status line on Today links to it. **Snapshot immutability** is stated and demonstrable: each morning's snapshot carries a timestamp and a content hash shown on the per-pick table. The **verdict rules are published** with thresholds, and any change to a threshold is dated in the changelog. A **monthly note** in News & Context reviews the month candidly, including the worst calls, written from real fields by the existing desk-note templates. And the product **never suppresses a neutral or negative result**: "No value detected" cards get the same design care as candidates, the parlay record shows its losses, and the page states when a segment is underperforming.

| | |
|---|---|
| User problem | Bettors have learned that every service's record is curated; a record shown as a footer panel is easy to distrust and easy to miss. |
| Why it helps | A primary destination with distinct treatments for four kinds of results, intervals, sample-size arithmetic, and standing copy reads as a discipline rather than a claim. |
| Advanced data preserved | Every existing backtest number, the calibration buckets, the dual-price experiment, the per-pick table, exports. |
| Trust effect | The core of the product's trust; also its most defensible marketing asset. |
| Effort | Medium for the page; closing-line value depends on the odds feed; intervals and segments are simple arithmetic on existing snapshots. |

---

## 12. Onboarding

### 12.1 Principles

Short and skippable: four screens, under ninety seconds, with "Skip" on every screen after the gate. Teach with the card, not with slides about the card. Bankroll is optional and paper by default. Nothing is taught only in onboarding; every concept reappears as a coach mark, a tooltip, or a lesson at the moment it matters.

### 12.2 The flow

**Screen 0 — the gate.** Age attestation (21+), a one-line statement that MONEYLINE is a research tool and not a sportsbook or betting advice, and the responsible-gambling helpline. Required.

**Screen 1 — what this is.** Three sentences: the model prices every game and shows its arithmetic; the app compares that price with the sportsbook's; most days it finds little or nothing, and says so. A link: "See how it has done" opens the Track Record.

**Screen 2 — how to read a card.** An annotated example card with four callouts: the verdict, model chance versus the book's price, the edge and expected return, and "loses 42% of the time."

**Screen 3 — try it.** The same card with a slider on the book's price. Dragging from −160 to −105 walks the verdict from *Avoid at this price* through *No value detected* and *Marginal value* to *Bet candidate* while the model chance stays at 58%. Caption: "The team didn't change. The price did. That is what an edge is."

**Screen 4 — your setup.** Detail level (Essentials, or "I already know EV and Kelly" → Full detail); explain terms on or off; your sportsbooks; time zone. Then an optional bankroll setup with "Keep it paper for now" as the prominent choice.

On landing in Today, three coach marks in sequence: the summary strip ("most games are a pass"), the first card's verdict pill, and the Track Record link.

### 12.3 Contextual lessons, mapped to the eight topics in the brief

| Topic | Trigger | Delivery |
|---|---|---|
| How to read the Today dashboard | First visit | Screen 2 and the three coach marks |
| What an edge means | First tap on "Edge" | Tooltip, then "How this is calculated" with the card's numbers, then the lesson |
| Why fair odds differ from sportsbook odds | Screen 3, and first tap on "Sportsbook's cut" | Slider demo; a lesson showing both sides' implied chances adding to more than 100% (−115 and −105 add to 104.7%) |
| Why high-probability bets can still lose | First graded loss on a candidate the user followed or logged | A calm note on the graded card and a lesson with a 100-bet simulator |
| Why parlays can be expensive | First Parlay Check | The house-cut bar and the singles comparison, then the lesson |
| How to compare sportsbook prices | First time two books differ on a card | "Best price" coach mark and a lesson on line shopping (no links to books) |
| How bankroll sizing works | Bankroll setup | Inline explanation of profile, fraction, shrinkage, and cap, then the lesson |
| What the model does not know | First expansion of "Context — not in the price" | Chip tooltips and the lesson "What the model can't see" (lineups, bullpens, weather, injuries, home field, umpires, travel) |

### 12.4 The education center

Ten lessons of under three minutes each, every one with a small interactive widget: what a price means; edge; the sportsbook's cut; expected return versus one outcome; variance and drawdowns; parlays; line shopping; bankroll and Kelly; what the model prices and what it cannot see; how the model works (the receipts, the BA paradox as the origin story). Plus the glossary generated from the terminology dictionary and the model changelog. Lessons are free, indexed, and linkable from every tooltip.

| | |
|---|---|
| User problem | The concepts that make the product valuable (edge, fair price, variance) are unfamiliar to the primary persona; a long tutorial would be skipped. |
| Why it helps | Four screens establish the reading model; contextual lessons arrive when the concept is live on screen. |
| Advanced data preserved | Full-detail users skip straight to their settings; nothing is gated behind lessons. |
| Trust effect | Screen 1 and the gate set expectations plainly before the first card is seen; the "try it" slider teaches that value is about price, not certainty. |
| Effort | Low to Medium — a flow, an interactive card, ten short lessons, and the coach-mark system. |

---
## 13. Mobile UX

### 13.1 Strategy: responsive web and a progressive web app first

The current app already stacks under 900 px; the redesign should treat the phone as the primary reading device for Today and build the card system mobile-first, then ship the result as an installable progressive web app. One codebase, no app-store review cycle for a betting-adjacent product while the design is still moving, and the same URLs for support and sharing. Native apps become worth the cost when push notifications and accounts are mature (Phase 3 or later), not before.

### 13.2 Layout on a phone

A five-item bottom bar: Today, Research, Parlay Check, Track Record, Bankroll. Today shows a sticky date bar with the summary strip beneath it, then one column of collapsed cards. Tapping a card opens the game detail as a full-height sheet with the three layers; swiping left or right moves to the next game in the current sort. "Show the numbers" renders key-value rows rather than tables; the few tables that must exist (the two-side price table, the per-leg parlay table) scroll horizontally inside their own container and never widen the page. Charts collapse to one headline number and a sparkline, with "Open chart" for the full version.

The bankroll widget becomes a single chip under the summary strip ("$1,000 · Balanced · this week −$12"), and the context feed folds into each card's context layer. Research opens a hub screen of five tiles rather than a dropdown.

### 13.3 Interaction rules

Tap targets of at least 44 px; body text at 15–16 px and chips no smaller than 13 px; primary actions in the lower half of the screen. Nothing depends on hover: tooltips become tap-to-open popovers with a close affordance. Disclosure state persists for the session so a user who opened "Why" on one card does not have to reopen it on the next. Pull-to-refresh updates prices and shows the new "as of" time. When offline, the last snapshot renders with an "as of" stamp and verdicts marked "may be out of date." Each card owns its own loading skeleton so a slow game never blocks the list.

### 13.4 Notifications (Phase 3, opt-in, off by default)

A daily summary at a time the user picks ("Today: 2 candidates, 10 no value, 3 waiting on data"), starter confirmations for games the user is tracking, and graded results for logged bets. Never a price-movement alert, never a stake, never a countdown, and quiet hours by default. Notification copy passes the same lint as product copy.

| | |
|---|---|
| User problem | Bettors check games on their phones, often in the hour before first pitch; the current desktop-first grid is unreadable there. |
| Why it helps | A mobile-first card list with a bottom bar and detail sheets matches how the primary persona actually uses betting products. |
| Advanced data preserved | Every layer is reachable on the phone; tables scroll rather than disappear; exports remain available. |
| Trust effect | Offline and stale states are explicit; notifications are informational and off by default. |
| Effort | Medium — mostly the responsive discipline of the card system plus the PWA manifest and service worker. |

---

## 14. Visual design system

### 14.1 Direction

"A modern sports analytics dashboard combined with a trustworthy personal-finance app" translates into a small number of decisions: calm surfaces with real spacing, sentence-case labels, tabular numerals everywhere numbers align, a monospace face reserved for prices as the product's analytical signature, and semantic color that is desaturated, sparse, and always paired with an icon and a word. The reference points are budgeting and brokerage apps that show money without excitement, and analytics dashboards that show data without noise. The product should look like it was made by people who would rather be right than exciting.

### 14.2 Dark and light

Build both from one token set from the first day; ship a refined dark theme in Phase 1 for continuity with existing users and evening use, ship the light theme in Phase 2, and default to the system preference once both exist. Use the light theme in marketing and onboarding screenshots, where the personal-finance association does the most work.

The refined dark theme lifts the current near-black: page `#0f1318`, surface `#161b22`, raised `#1c222b`, borders `#262c36`, primary text `#e6e9ef`, secondary text `#9aa4b2`. The light theme: page `#f6f7f9`, surface `#ffffff`, borders `#e3e6ea`, primary text `#14171c`, secondary `#5b6472`. Both keep `color-scheme` set in the document so there is never a flash.

### 14.3 Typography

Inter (or an equivalent humanist sans) for everything except prices: 16 px body on desktop, 15 px on phones, 13 px minimum for chips, 20–24 px for section headings, 28–32 px for the one hero number on a page. The **price face** — IBM Plex Mono or JetBrains Mono with `font-variant-numeric: tabular-nums` — is used for American odds, probabilities inside tables, units and records, timestamps, and team codes in tables. It is never used for labels, body copy, or headings. Uppercase letter-spaced text is retired except for optional 11 px eyebrows in dense tables. Sentence case everywhere else.

### 14.4 Color

One brand accent, used for links, focus rings, primary buttons, and the active navigation item: a sober blue such as `#2457A0` (light) / `#6FA8E0` (dark). Verdict and status colors are desaturated and used as 12% (light) or 15% (dark) tinted pill backgrounds with solid-color text and an icon. The values below were checked against WCAG AA: each text color reaches at least 4.5:1 on its own tinted pill over the theme surface (light-theme values land between 5.0:1 and 6.1:1; dark-theme values between 4.9:1 and 5.9:1).

| Meaning | Light | Dark | Icon |
|---|---|---|---|
| Bet candidate | `#276A4D` | `#4FB08A` | filled circle with check |
| Marginal value | `#8A5A12` | `#D9A441` | half-filled circle |
| No value detected | `#5B6472` | `#9AA4B2` | empty circle |
| Avoid at this price | `#9A4508` | `#E08A3C` | circle with slash |
| Insufficient data / waiting | `#5B6472` dashed outline | `#9AA4B2` dashed outline | dashed circle |
| Stale / as-of warnings | `#8A5A12` | `#D9A441` | clock |
| Context, not in the price | neutral border, flag icon | same | flag |
| Win (record) | `#276A4D` | `#4FB08A` | check |
| Loss (record) | `#8F3A4C` | `#DD7F98` | minus |

No saturated red or green anywhere; the loss color is a muted rose, not a stop sign, and wins are recorded, not celebrated. Card borders (`#262c36` on the dark surface) are decorative and deliberately low-contrast; cards are identified by their surface and spacing, not by their outline. Charts follow a single-accent-plus-gray rule: the series that matters in the accent, comparisons in gray, confidence bands as light gray fills, and never a red/green area fill.

### 14.5 Spacing, cards, and layout

An 8 px grid. Cards have 16 px padding on phones and 20 px on desktop, a 12 px radius, a 1 px border in dark and a soft shadow in light. The content column is capped around 780 px with a 320 px rail on wide screens. No hero sections, no decorative imagery, no team logos or headshots (initial blocks in team-ish hues remain fine).

### 14.6 Icons, badges, tables, charts, motion

Icons are a single outline set (Lucide or equivalent) at 20 px, always accompanied by text when they convey status. Badges are 24 px pills with an icon and sentence-case text. Tables appear only in Full detail: sticky headers, right-aligned tabular numerals, 40 px rows, sort indicators, and on phones either a horizontal scroll container or a card transformation. Charts have plain-English titles ("Model's units over time, with the break-even line"), light gridlines, annotated endpoints, bucket counts on calibration plots, no 3D, gradients, or dual axes, and a one-sentence text summary for screen readers. Motion is limited to 150–200 ms disclosure and state transitions; count-up numbers and needle animations are retired because they read as a slot machine, and `prefers-reduced-motion` disables what remains.

### 14.7 Accessibility

WCAG 2.2 AA as the floor: 4.5:1 text contrast and 3:1 for UI elements in both themes (the pill palette above is chosen to pass on its tints), visible focus rings, full keyboard reach with the existing shortcuts documented, `aria-live="polite"` on verdict regions, verdicts announced as words, table semantics preserved for screen readers, 44 px targets, and no information carried by color alone.

### 14.8 Visual hierarchy rules for any card or panel

One verdict, at the top, is the strongest element. At most three type sizes per card. The model chance and the book price have equal weight; the fair price is secondary. Honesty furniture (sample chip, as-of stamp) is muted but never below 13 px. Calls to action are text or outline buttons, never large filled green buttons.

### 14.9 What the product must never resemble

A sportsbook: no odds boxes styled as buttons, no promo banners, no bright green filled buttons, no "boosts." A casino: no gold, neon, confetti, or celebratory animation on wins. A tout: no flames, locks, fire emoji, "expert" avatars, or countdowns.

| | |
|---|---|
| User problem | The terminal styling signals "not for me" to the primary persona and "casino" to nobody, but its saturated red/green and animated numbers still encourage impulse. |
| Why it helps | Calm surfaces, sentence case, and a price face used sparingly keep the analytical identity while making the interface readable and unhurried. |
| Advanced data preserved | Tables, receipts, and charts remain, with better hierarchy; the monospace signature survives where it earns its place. |
| Trust effect | Restraint is the visual form of honesty; the desaturated verdict palette and recorded-not-celebrated results reinforce it. |
| Effort | Medium — a token system, a component library pass, and two themes; most of the work is applying it consistently. |

---
## 15. Prioritized roadmap

The roadmap is sequenced so that each phase ships something a user can feel and each phase's dependencies are resolved by the one before it. Effort assumes one full-stack engineer and one designer, with the existing v1/v2 codebase and its test discipline intact; the smoke-test suite remains the gate for every release.

### Phase 0 — Foundations (2–3 weeks)

Design tokens and the two-theme system; the terminology dictionary and the copy lint; the verdict-engine specification with unit tests against hand-checked cases (Appendix A); the explanation-generator specification (Appendix B); the honesty-furniture components (sample chip, as-of stamp, disclaimer, "not in the price" chip); an odds-provider evaluation with a two-week spike on the leading candidate; legal review kicked off on data licensing, tout and advertising rules, and payment processing; product analytics events for comprehension and pass-rate metrics.

Exit criteria: tokens applied to one existing panel in both themes; verdict engine passing its fixture tests; a signed-off odds provider and a legal memo listing blockers.

### Phase 1 — Today (5–6 weeks)

Odds feed integration with opening, current, and closing line capture per book; the verdict engine and signal strength in the API; the explanation generator; the game card and game detail with three layers; the Today page with summary strip, sections, and designed states; the five-item navigation and the Research hub shell; detail level and explain-terms preferences; the Track Record page with the live record, the candidates-only record from feed go-live, segments, intervals, calibration, and the historical section under its banner; the home-field adjustment shipped as a dated model version with its record tracked from that date (see 16.1); the progressive web app manifest and offline snapshot.

Exit criteria: a primary-persona tester explains fair price and edge unprompted after one session; every card state in section 5.4 reachable in QA; Track Record renders four records with no shared number; smoke tests green; cold start still under five seconds.

### Phase 2 — Bankroll and trust (5–6 weeks)

Accounts and sync; bankroll setup, profiles, the stake card with shrinkage and caps, the variance line; My bets with closing-line capture and grading; Parlay Check; onboarding, coach marks, and the education center with ten lessons; the responsible-use toolkit; the light theme; share cards with the disclaimer baked in; billing and the Pro tier.

Exit criteria: no dollar figure appears without a bankroll and positive expected return (enforced by tests); a logged bet grades correctly with its closing price; onboarding completion above 70% in testing; billing live with the free tier unchanged.

### Phase 3 — Depth and growth (6–8 weeks)

Research hub restyle (Players, Matchups, Teams & Season, News & Context) on the card system; multi-book comparison with preferred books and best-price flagging; informational notifications; the data status page; the monthly honest note; a full accessibility audit; performance work on feed concurrency; export improvements.

### Later

Native apps once notifications and accounts are proven; additional bet types (run lines and totals require the model to produce run distributions, which is model work, not UI work); additional sports only with their own graded models; community features only if they can be built without social proof on picks.

### Effort and impact summary

| Recommendation | Phase | Effort | Impact | Depends on |
|---|---|---|---|---|
| Token system and themes | 0 | Medium | High (everything sits on it) | — |
| Terminology dictionary and copy lint | 0 | Low | High | — |
| Verdict engine and signal strength | 0–1 | Medium | Very high | Odds feed for prices |
| Odds feed with line capture | 1 | High | Very high | Provider contract, legal |
| Game card and game detail | 1 | Medium | Very high | Verdict engine, explanation generator |
| Today page and navigation | 1 | Medium | Very high | Card |
| Explanation generator | 1 | Medium | High | Receipts (exist) |
| Track Record redesign | 1 | Medium | Very high | Snapshots (exist), closing lines |
| Home-field adjustment (versioned) | 1 | Low–Medium | High (removes a known bias) | Changelog, record by version |
| Detail level and explain toggles | 1 | Low | High | — |
| Bankroll, profiles, stake card | 2 | Medium | High | Accounts |
| My bets with CLV | 2 | Medium–High | High (retention) | Odds feed, accounts |
| Parlay Check | 2 | Low–Medium | Medium–High | Existing math |
| Onboarding and education center | 2 | Low–Medium | High | Dictionary |
| Responsible-use toolkit | 2 | Low | High (trust, compliance) | Accounts |
| Light theme | 2 | Low (if tokens done) | Medium | Tokens |
| Research hub restyle | 3 | Medium | Medium | Card system |
| Multi-book comparison UI | 3 | Medium | Medium–High (Pro value) | Odds feed stable |
| Notifications | 3 | Medium | Medium | Accounts, PWA |

---

## 16. Risks and open questions

### 16.1 The home-field omission is a predictable bias in the candidates record

This is the most important technical risk in the document. Major League home teams win roughly 53–54% of games. A pricing chain with no home term prices the home side too low by about three to four points at even matchups. Sportsbooks price home field in; the model does not; so the model will systematically "see value" on road teams. The candidates record would then be tilted against the model from its first day, for a reason that has nothing to do with the offense and run-prevention insight the model is built on. Recommendation: ship a home-field term in Phase 1 as a dated model version, applied to both prices, with the changelog showing each version's record from its own date. If the team prefers the purer experiment pattern used for the starter adjustment, run it as a third graded price for one month and then fold it in. Either way, do not launch the candidates record without it.

### 16.2 Other risks

**The model's game-level edge may be small or nil.** The product must be worth paying for even in a season where the candidates record is flat. It is: price comparison, closing-line value on your own bets, disciplined sizing, honest parlay math, and the research desk have value independent of the model's edge, and the copy never promised one. Marketing should not quote the candidates record until it has at least a few hundred graded picks.

**Verdict thresholds could be tuned to early results.** Thresholds are published, changed only with a changelog entry, and never changed to make a past month look better. The record is reported by bucket precisely so that tuning is visible.

**Users may read "Bet candidate" as a pick regardless of design.** Mitigations are structural (the pass rate, the "loses X% of the time" line, no bet buttons, no links) and are measured: track the share of users who open "Why" and the share who visit the Track Record. If the numbers say the label is being read as a pick, the fallback label is "Price looks favorable," which is duller and safer.

**Odds-feed cost and reliability.** Budget for a paid provider; design every price surface for absence and staleness; keep manual entry forever.

**Data licensing.** Commercial use of the keyless MLB Stats API needs a legal answer before charging money; the fallback is a licensed stats provider, which changes the cost base but not the design.

**Regulatory drift.** Tout and betting-information services are lightly regulated today and several states have discussed changing that; keep the product on the research side of the line (no links, no affiliate revenue, no stakes in notifications) so that any future rule is easy to meet.

**Payment processing.** Confirm the processor's policy on betting-information subscriptions before Phase 2 billing work.

**Small-sample seasons.** April is a small-sample month every year; the verdict engine withholds verdicts under the published threshold, and the product needs good content for those weeks (the education center, last season's record, the historical tests).

### 16.3 Open questions for the team

1. Which odds provider, at what cost, and for which books? The verdict should be computed on prices from the user's chosen books, with "best available" shown as information.
2. What is the model's typical probability error to seed the signal-strength gap ratio, and who owns revising it from live calibration?
3. What is the rule for moving the staking-chance weight toward the model — a fixed sample threshold, a closing-line-value threshold, or a manual decision with a changelog entry?
4. Should the "All leans" record stay public? It is honest but not bettable at flat odds, and it may confuse readers next to the candidates record. Recommendation: keep it, labeled "every game, flat one unit — a model check, not a betting record."
5. Free-tier limits on the research desk: daily caps or feature gates?
6. Does the team want to keep the terminal boot sequence as an easter egg for existing users?
7. What minimum sample size should gate any external claim about the candidates record?

---

## 17. Final recommendation

Keep the doctrine and change the delivery. MONEYLINE's model, receipts, refusal states, and public grading are rare and valuable; its terminal presentation is the only thing standing between that value and a paying audience. Build one three-layer card system on a published verdict engine, make Today the front door and Track Record the public home page, put money in one bankroll area with shrunk Kelly sizing and real limits, and refresh the visual system toward calm, sentence-case, tabular-numeral restraint with a monospace price face as the surviving signature.

Ship in this order: foundations and legal review; Today with a licensed odds feed, the verdict engine, the explanation generator, the redesigned record, and the home-field fix; then bankroll, My bets with closing-line value, Parlay Check, onboarding, and the Pro tier; then the research hub, multi-book comparison, and notifications. Do not ship "Beginner mode" as a mode, "Find an Edge" as a destination, "Aggressive" as a profile, "Confidence" as a label, or a featured parlay as a daily feature.

The commercial argument is that the market is crowded with products that sell certainty and thin on products that sell discipline. A product that tells its users "nothing today" more often than not, shows every loss, and sizes stakes as if its own edge might be smaller than it looks will lose the users who wanted a tout and keep the ones who wanted a tool. Those are the users who renew.

---
# Part 2 — UI/UX Implementation Plan

This part converts the Phase 0–2 recommendations into build-ready specifications. Each page lists its purpose, regions, components, data requirements, user flows, and acceptance criteria. Acceptance criteria are written to be testable in the same evidence discipline as the existing smoke-test spec: a criterion passes only when it has been executed and observed. Component definitions, API additions, and the rule specifications follow the pages.

Conventions: `DTO` names refer to the API shapes in section P2.2; "both levels" means Essentials and Full detail; "all states" means every designed state listed for the page.

---

## P1. Pages

### Page 1 — Today (`/today`, default route)

**Purpose.** Answer "which games deserve my attention?" in one screen, with pass as a normal result.

**Regions.** Date bar; data status line; summary strip; filter and sort bar; card sections (*Worth a look*, *No value detected*, *Waiting on data*, *In progress and final*); right rail on wide screens (daily summary, bankroll widget, Track Record snapshot, context feed); footer with disclaimer and helpline.

**Components.** `DateBar`, `DataStatusLine`, `SummaryStrip`, `FilterSortBar`, `GameCard` (collapsed and expanded), `SectionHeader` with first-time explainer, `BankrollWidget`, `RecordSnapshot`, `ContextFeed`, `HonestyFooter`, `CardSkeleton`.

**Data requirements.** `GET /api/today?date=&books=` returning `TodayDTO` (as-of timestamps for stats, prices, and model version; summary counts; an array of `GameCardDTO`). Prices come from the odds ingestion layer with a 5–10 minute TTL and per-book timestamps. The evaluation (verdict, signal, risk, reasons, takeaway) is computed server-side by the verdict engine and explanation generator so that every client renders identical answers. Stake data is included only for an authenticated user with a bankroll.

**User flows.**

1. *Scan and decide.* Open app → read summary strip → scan *Worth a look* → tap a card's "Why" → tap "See full breakdown" or move on.
2. *Nothing today.* Open app → summary shows 0 candidates → read the calm empty state → optionally open a *No value* card to see why → leave.
3. *Missing price.* Card shows "No price loaded" → tap "Add a price" → enter −115 → verdict computes inline via `POST /api/evaluate` → card updates with "your price" labeling.
4. *Follow the day.* Switch sort to "By start time" → preference persists → in-progress games show live score without verdict → final games show result and grade.
5. *Yesterday.* Tap Yesterday → graded cards with both prices' results → link to Track Record.

**Acceptance criteria.**

- [ ] Every card renders a verdict from `GameCardDTO.evaluation.verdict`; no client-side verdict logic exists.
- [ ] No card shows edge or expected return unless a price with a book name and timestamp is present in the DTO.
- [ ] Summary counts equal the number of cards in each section for every date tested, including a date with zero candidates.
- [ ] Each state in strategy section 5.4 (no candidates, feed unavailable, stale price, starters unconfirmed, small sample, off-season, postponed, in progress) is reachable with a fixture and renders its designed copy with no raw error text.
- [ ] Sort and filter choices persist across reloads; "Candidates only" hides every non-candidate section.
- [ ] Manual price entry produces the same evaluation as the server would for the same inputs (fixture comparison).
- [ ] In-progress games show no verdict and freeze the pre-game price in the DTO for grading.
- [ ] Collapsed card height fits four lines of content on a 375 px wide viewport without truncating the takeaway.
- [ ] Keyboard: Tab reaches every card action; Enter opens the breakdown; "/" focuses search; 1–5 switch destinations.
- [ ] Screen reader announces "Bet candidate, Red Sox" as text for the pill; no verdict is conveyed by color alone (axe audit clean).
- [ ] The disclaimer and helpline footer and the data status line are present in both levels and cannot be collapsed.
- [ ] First contentful paint of Today from a warm cache under 1.5 s on a mid-range phone; skeletons per card, never a blank list.

---

### Page 2 — Game detail (`/game/{gamePk}`)

**Purpose.** The full breakdown: the same three layers as the card at full width, plus the tool to check any price.

**Regions.** Header (identity, starters, status, share); verdict block with takeaway; price comparison (two-side table in Full detail, key-value rows in Essentials); "Why the model leans"; "Why it's a candidate" (or "why there's no value"); "Context, not in the price"; risk; stake card (conditional); "The numbers" (season and starter-adjusted prices, receipts, line movement, Kelly arithmetic); "Check a price"; related links (Track Record filtered to this verdict and signal, Team strength for both teams, Matchups, player cards for starters).

**Components.** `GameHeader`, `VerdictBlock`, `PriceCompare`, `ReasonList`, `ContextChips`, `RiskPanel`, `StakeCard`, `Disclosure`, `ReceiptTable`, `LineMovement`, `KellyBreakdown`, `PriceChecker`, `RelatedLinks`, `ShareCard`.

**Data requirements.** `GET /api/game/{gamePk}` returning `GameDetailDTO` = `GameCardDTO` plus `receipts` for both teams (inputs, coefficients, contributions, predicted runs, Pythagorean strength, log5 result), `line_history` per book per side, `both_sides` evaluation table, `kelly` arithmetic (only with bankroll), and `links`. `POST /api/evaluate` for the price checker (pure function of model chances and a price). Share card rendering via a server-side image endpoint `GET /api/share/game/{gamePk}.png` that bakes in the disclaimer and the as-of stamp and never includes a stake.

**User flows.**

1. *Understand a candidate.* Land from a card → read verdict and takeaway → read three reasons → expand context → read risk → (if bankroll) read stake → "Log this bet" → Bankroll → My bets pre-filled.
2. *Check my book's price.* Enter a price not in the feed → evaluation updates with "your price" label → compare with best available.
3. *Audit the math.* Open "The numbers" → open "How this is calculated" on edge → see the formula with the actual figures → open receipts → see inputs × coefficients → contribution sums equal the displayed predictions.
4. *Go deeper.* Tap a starter → player card; tap a team → Team strength; tap "See how candidates have performed" → Track Record with the filter applied.
5. *Share.* Tap share → preview of the image with disclaimer → copy link or download image.

**Acceptance criteria.**

- [ ] Receipt contributions sum to the displayed predicted runs within rounding for both teams; the Pythagorean and log5 steps reproduce the displayed model chance.
- [ ] "Why the model leans" bullets reference only priced inputs; a fixture with a team that has an injury flag and a negative pulse must not mention either in that list.
- [ ] Context chips render with the "not in the price" label and open their evidence (IL entry, transaction, pulse item list).
- [ ] Line movement shows opening, current, and (after first pitch) closing price with timestamps; when only one snapshot exists it says so.
- [ ] The stake card is absent for users without a bankroll and for any side with expected return ≤ 0 (tested with fixtures for both).
- [ ] The price checker's result matches `POST /api/evaluate` for the same inputs and labels the result "your price."
- [ ] The share image contains the verdict, the two prices, the sample chip, the as-of stamp, and the disclaimer, and never contains a dollar stake.
- [ ] All disclosures remember their state within the session; Full detail opens all three layers by default.
- [ ] Deep-linking to a final game shows the graded result for both prices and no verdict.

---

### Page 3 — Track Record (`/record`)

**Purpose.** The public proof and the honest explanation of what it proves.

**Regions.** Hero (live record with since-date, counts, record, units, return with interval, average CLV, "What this proves"); three records side by side (all leans, candidates, parlays); the season-versus-starter experiment; segment tables with sample notes; live calibration chart; closing-line value block; historical tests under the banner; methodology and changelog; "how many bets it takes" explainer; per-pick table with export.

**Components.** `RecordHero`, `ProofStatement`, `RecordTriplet`, `ExperimentCompare`, `SegmentTable`, `CalibrationChart`, `CLVBlock`, `HistoricalBanner`, `BacktestPanels` (existing, restyled), `Changelog`, `SampleSizeExplainer`, `PickTable`, `ExportButton`.

**Data requirements.** `GET /api/record?segment=&from=&to=&group_by=` returning `RecordDTO` with totals (picks, graded, wins, losses, pushes, units at recorded prices, units at flat −110 for the all-leans record, return on money risked, 95% interval), CLV summary, buckets for the requested grouping (each with n and interval), and picks (date, game, side, price used, book, model chance, verdict, signal, result, units, closing price, CLV). `GET /api/record/calibration` for live buckets. `GET /api/model/versions` for the changelog with each version's record from its date. Historical artifacts from the existing `/api/track-record` and `/api/backtest`.

**User flows.**

1. *Evaluate before trusting.* Logged-out visitor lands here → reads hero and proof statement → opens candidates record → sees intervals and sample notes → opens historical section → proceeds to Today.
2. *Check a claim.* From a card's "See how candidates have performed" → segment view pre-filtered to the signal level → reads bucket n and interval.
3. *Audit a pick.* Open the per-pick table → find yesterday's game → see price used, closing price, CLV, result → export CSV.
4. *Understand a change.* Open the changelog → see the home-field version date → see each version's record separately.

**Acceptance criteria.**

- [ ] The four record types share no numeric total, no chart series, and no color; the historical section's banner is visible whenever any historical figure is on screen.
- [ ] Hero totals are internally consistent (wins + losses + pushes = graded ≤ picks) and identical after a grading job runs twice.
- [ ] Every bucket under 50 graded picks shows the "too small to read" note; every total shows n and the since-date.
- [ ] The interval on return is computed by a stated method (documented in methodology) and re-derivable from the per-pick export.
- [ ] Candidates record starts at the odds-feed go-live date and says so; no candidate is graded at a price that was not in its frozen snapshot.
- [ ] CLV per pick equals the difference between the implied chance at the closing price and at the price used, in points, with sign convention documented.
- [ ] The calibration chart shows bucket counts and a 45-degree reference; buckets with n under 30 are visually de-emphasized.
- [ ] The proof statement's numbers (picks, units swing) update from the DTO, never from hard-coded copy.
- [ ] Export re-parses with the documented columns; pending picks are excluded from totals and marked pending in the export.

---

### Page 4 — Bankroll (`/bankroll`)

**Purpose.** One place for the user's money: setup, sizing, logged bets, limits.

**Regions.** Setup (bankroll amount, profile with plain descriptions, paper mode, limits); stake calculator (any model chance and price → stake with the full chain); My bets (log, grading, CLV, comparison with the model); limits and cooling-off; resources.

**Components.** `BankrollSetup`, `ProfilePicker` (Higher variance selectable only here, after its description), `StakeCard`, `KellyBreakdown`, `VarianceLine`, `BetLog`, `BetRow`, `CLVSummary`, `ModelComparison`, `LimitsPanel`, `CoolingOffSwitch`, `ResourcesPanel`.

**Data requirements.** `GET/PUT /api/me/bankroll` (`BankrollDTO`: amount, profile, unit, paper_mode, weekly_loss_limit, session_reminder, cooling_off_until, updated_at). `POST/GET /api/me/bets` (`BetDTO`: gamePk, side, price, book, stake, is_paper, placed_at, closing_price, result, units, clv). A grading job that captures the closing price at first pitch and grades at final. `GET /api/me/summary` for the widget. Stake computation via `POST /api/stake` (pure function: model chance, market de-vigged chance, price, bankroll, profile → staking chance, full Kelly, fraction, cap, stake, variance projection).

**User flows.**

1. *Set up.* Enter bankroll → read the definition ("money set aside that you can afford to lose") → pick Conservative or Balanced → set an optional weekly loss limit → keep paper mode.
2. *Size a bet.* From a candidate's stake card → read the chain → "Log this bet" → confirm paper or real → entry appears in My bets as pending.
3. *Grade and learn.* Next day → bet graded with closing price and CLV → the comparison line updates ("you took a better price than the close 3 of 5 times").
4. *Hit a limit.* Weekly loss limit reached → stakes hidden with a plain notice → resources one tap away → limit resets on schedule.
5. *Cool off.* Toggle cooling-off for 7 days → all dollar figures hidden immediately → turning off requires a 24-hour delay.

**Acceptance criteria.**

- [ ] No dollar figure appears anywhere in the product without a bankroll set; enforced by a test that renders every stake surface with `bankroll = null`.
- [ ] Stake equals min(fraction × full Kelly on the staking chance, profile cap) × bankroll, rounded to the nearest dollar; fixtures cover the worked example ($9 / $18 / $27 on $1,000 at model 58%, price −115/+105) and a no-value case (stake absent).
- [ ] The staking-chance weight is a published constant shown on the stake card in Full detail.
- [ ] Parlay stakes use the parlay cap (half the singles cap).
- [ ] Higher variance cannot be selected during onboarding and shows its drawdown description before selection.
- [ ] Logged bets are graded from real final scores; the closing price is the last feed snapshot before first pitch and is stored with the bet.
- [ ] Cooling-off hides all stakes and dollar figures within one render and enforces the turn-off delay server-side.
- [ ] Limits, cooling-off state, and bankroll survive restart and sync across devices.
- [ ] The word "recommended" does not appear on any bankroll surface (copy lint).

---

### Page 5 — Parlay Check (`/parlay`)

**Purpose.** Tell the user whether a parlay is worth it, and show the singles alternative.

**Regions.** Leg list (add from Today or from the page's game list); verdict and takeaway; the three numbers; house-cut comparison bar; singles comparison; expected return and risk; correlation notes; stake (conditional); the numbers.

**Components.** `LegRow`, `LegPicker`, `ParlayVerdict`, `ThreeNumbers`, `HouseCutBar`, `SinglesCompare`, `ParlayRisk`, `CorrelationNotes`, `StakeCard`, `ParlayMath`.

**Data requirements.** `POST /api/parlay/evaluate` (legs with gamePk and side; optional book parlay odds) returning `ParlayDTO`: combined chance, fair odds, book odds (entered or compounded, with a flag), edge, expected return per $100, house cut on parlay vs singles, per-leg evaluations, correlation warnings, verdict, takeaway, chance of losing, required win rate, and Kelly arithmetic when a bankroll exists. Same-game legs return a 400 with the styled message; more than six legs likewise. `POST /api/parlay/log` remains for the paper record.

**User flows.**

1. *Check a slip.* Add three legs → enter the book's parlay price → read *Poor value* and the takeaway → read singles comparison → remove the weakest leg → verdict updates → log or discard.
2. *Learn.* First visit → the house-cut bar coach mark → open the lesson.
3. *Refused.* Add two legs from the same game → inline refusal with the reason.

**Acceptance criteria.**

- [ ] Fixtures reproduce: two 55% legs → 30.25%, fair about +230; two −110 legs compound to about +265; the three-favorites slip (58/60/56% at −150/−160/−140) → expected return about −$9.50 per $100 and verdict *Poor value*; the Boston/San Diego/Chicago slip → about +$6.80 per $100, verdict *Marginal*, singles comparison stating Boston alone is better.
- [ ] House-cut bar values for coin-flip legs at −110 match 4.5%, 8.9%, 13.0%, 17.0%, 20.8% for one to five legs.
- [ ] Same-game legs and more than six legs are refused in the UI and by the API.
- [ ] The independence assumption is stated on the page in both levels.
- [ ] No "model slip of the day" or any featured parlay appears on the page by default.
- [ ] Stake appears only with positive expected return and a bankroll, using the parlay cap.

---

### Page 6 — Onboarding and Settings (`/welcome`, `/settings`)

**Purpose.** Set expectations plainly, teach the card, capture preferences, keep bankroll optional.

**Regions.** Gate; what this is; how to read a card; try it (price slider); your setup; optional bankroll. Settings: detail level, explain terms, theme, my sportsbooks, time zone, notifications (Phase 3), subscription, responsible-use links.

**Components.** `GateScreen`, `IntroScreen`, `AnnotatedCard`, `PriceSliderDemo`, `SetupScreen`, `BankrollPrompt`, `CoachMark`, `SettingsForm`.

**Data requirements.** `GET/PUT /api/me/preferences` (`PreferencesDTO`: detail_level, explain_terms, theme, books, tz, onboarding_completed_at, coach_marks_seen). The slider demo uses `POST /api/evaluate` or an identical client-side pure function verified against server fixtures.

**User flows.**

1. *New user.* Gate → intro → annotated card → slider flips the verdict → setup → "Keep it paper for now" → Today with three coach marks.
2. *Experienced user.* Gate → skip → setup with "I already know EV and Kelly" → Full detail, explanations off → Today.
3. *Change my mind.* Settings → detail level → Essentials → Today re-renders with layers collapsed; verdicts unchanged.

**Acceptance criteria.**

- [ ] The gate cannot be skipped; every other screen can.
- [ ] The slider demo, at a 58% model chance, shows *Avoid at this price* at −160, *No value detected* at −140, *Marginal value* at −130, and *Bet candidate* at −120 and shorter, with the model chance visibly unchanged (values follow the Appendix A thresholds).
- [ ] Completion time under ninety seconds in usability testing when bankroll is skipped.
- [ ] Preferences apply immediately and persist; changing detail level never changes any verdict, number, or threshold (snapshot test).
- [ ] Coach marks appear once per account and never again unless reset in settings.
- [ ] The helpline is present on the gate, the bankroll prompt, and the settings page.

---

### Page 7 — Research hub (`/research/...`, Phase 3 restyle)

**Purpose.** Preserve every research surface (Players, Matchups, Teams & Season, News & Context, Learn) on the card system and terminology, with shareable URLs.

**Scope for Phase 1–2.** Routes and the hub shell exist from Phase 1 so nothing is lost; panels render with the new tokens and dictionary labels but keep their layouts. Phase 3 restyles each surface.

**Acceptance criteria (Phase 1).**

- [ ] Every v2 tab is reachable from the hub, with redirects from the old tab routes.
- [ ] Every 2026-derived number keeps its games-played label; every refusal state (2027, hitter versus pitcher, no salary data) renders with sentence-case copy.
- [ ] Media pulse appears only inside the context layer with its evidence list, never as a price input.
- [ ] Learn hosts the glossary generated from the dictionary and the model changelog.

---
## P2. Components, data, and APIs

### P2.1 Component library

Every component declares its layers (answer, explanation, numbers), its states (loading, empty, error, stale), and which honesty furniture it must render. Components consume labels only from the terminology dictionary.

| Component | Purpose | Inputs | States and rules |
|---|---|---|---|
| `VerdictPill` | The one-word answer | verdict, side, size | Icon + sentence-case text; tinted background; `aria-label` includes the side; never color-only |
| `Takeaway` | One-sentence explanation of the verdict | text from the explanation generator | Mentions the value side when it differs from the lean |
| `PriceCompare` | Model chance, book price, fair price | evaluation, price_used, fair | Essentials: three values in a row; Full detail: two-side table across books; book name and as-of stamp mandatory |
| `EdgeStat` | Edge in points and expected return per $100 | edge_pts, ev_per_100 | Hidden entirely when no price; "How this is calculated" expander with real figures |
| `SignalChip` | Signal strength | level, provisional flag | Tooltip text is fixed: disagreement, not certainty; "provisional" suffix until bucket n ≥ 200 |
| `RiskRow` | Chance of losing, payout shape, uncertainty | chance_lose, price, uncertainty | Essentials: "loses X% of the time"; Full detail: all four elements |
| `SampleChip` | Games in the estimate | gp values, threshold | Amber below 60 games; verdict withheld below 30 (engine rule) |
| `AsOfStamp` | Data freshness | timestamp, ttl | Amber when older than 15 minutes; text "as of h:mm" |
| `ContextChip` | Context not in the price | type, label, evidence link | Flag icon; always carries "not in the price" on hover/tap; opens evidence |
| `ReasonList` | Why the model leans / why it is a candidate | reasons[] | Max three lean bullets; separate candidate line; sample sentence always last |
| `Disclosure` | Layer expander | title, default open, level | Remembers state per session; animates 150–200 ms; honors reduced motion |
| `ReceiptTable` | Inputs × coefficients → contributions | receipts | Contributions sum to prediction; monospace price face for numbers |
| `LineMovement` | Open → current → close | line_history | One-snapshot case says so |
| `KellyBreakdown` | Stake arithmetic chain | stake computation | Shows model chance, market chance, staking chance, full Kelly, fraction, cap, rounding |
| `StakeCard` | Dollar stake and consequences | stake, bankroll, profile | Absent without bankroll or with EV ≤ 0; "paper" label until confirmed; variance line |
| `HonestyFooter` | Disclaimer, helpline, versions | model version, sources | Present on every route; not collapsible |
| `SummaryStrip` | Daily counts | summary | Counts are tappable filters |
| `SectionHeader` | Group header with first-time explainer | title, explainer | Explainer shows once per account |
| `RecordHero`, `RecordTriplet`, `SegmentTable`, `CalibrationChart`, `CLVBlock`, `HistoricalBanner`, `Changelog` | Track Record | RecordDTO | Four record types never share a series; small-bucket notes; banner persistent |
| `HouseCutBar`, `SinglesCompare`, `ParlayVerdict` | Parlay Check | ParlayDTO | Singles comparison always rendered when legs ≥ 2 |
| `CoachMark` | First-encounter teaching | key, text, learn link | Once per account; dismissible; never blocks a verdict |
| `PriceChecker` | Manual price entry | side, book | Validates American odds; "your price" label on results |
| `ShareCard` | Image export | gamePk | Server-rendered; disclaimer and as-of baked in; no stakes |

### P2.2 API additions and changes

All endpoints keep the existing error envelope `{"error": {"code", "message"}}` and the existing caching and coalescing rules.

| Endpoint | Purpose | Key fields |
|---|---|---|
| `GET /api/today?date&books` | Today page | `as_of {stats, prices, model_version}`, `summary {games, candidates, marginal, no_value, insufficient, live, final}`, `games: GameCardDTO[]` |
| `GET /api/game/{gamePk}` | Game detail | `GameCardDTO` + `receipts`, `line_history`, `both_sides`, `kelly?`, `links` |
| `POST /api/evaluate` | Pure verdict for any chances and price | in: `p_season, p_adj?, price, gp_home, gp_away, starters_confirmed, price_age_s` → out: `EvaluationDTO` |
| `POST /api/stake` | Pure stake computation | in: `p_model, p_market_devig, price, bankroll, profile, is_parlay` → out: staking chance, full Kelly, fraction, cap, stake, projection |
| `GET /api/record?segment&from&to&group_by` | Track Record | totals with interval, CLV summary, buckets, picks |
| `GET /api/record/calibration` | Live calibration buckets | bucket, n, predicted mean, actual rate |
| `GET /api/model/versions` | Changelog | version, date, description, record since date |
| `GET /api/status` | Data status page | per-source last success, cache age, state |
| `POST /api/parlay/evaluate` | Parlay Check (supersedes `/api/parlay/price`) | combined chance, fair, book (entered or compounded flag), edge, EV, house cut parlay vs singles, per-leg evaluations, correlation notes, verdict, takeaway |
| `GET/PUT /api/me/preferences` | Settings | detail_level, explain_terms, theme, books, tz, coach_marks_seen |
| `GET/PUT /api/me/bankroll` | Bankroll | amount, profile, unit, paper_mode, weekly_loss_limit, cooling_off_until |
| `POST/GET /api/me/bets` | My bets | BetDTO; grading job sets closing price, result, units, CLV |
| `GET /api/share/game/{gamePk}.png` | Share card | server-rendered image |

`GameCardDTO` (abridged):

```
gamePk, status, start_time, venue
away { team_id, code, name, gp }      home { ... }
probables { away {id, name, confirmed}, home {...} }
model { season {p_home, fair_home, fair_away},
        adj    {p_home, fair_home, fair_away} | null, blend_w }
prices { home: [{book, american, implied, updated_at, opening}], away: [...] }
evaluation {
  side, verdict, verdict_reason, signal, signal_provisional,
  edge_pts, ev_per_100, breakeven, chance_lose, volatility, uncertainty,
  price_used {book, american, updated_at},
  flags [stale | starters_unconfirmed | small_sample | prices_disagree],
  avoid_note?, sample {gp_home, gp_away, label}
}
reasons { lean: [...], candidate: [...], context: [...] }
takeaway
stake? { amount, pct, profile, is_paper, projection }
```

### P2.3 Data model additions

`line_snapshots` — gamePk, book, side, american, captured_at, kind (opening | current | closing). Closing is the last snapshot before first pitch. `daily_snapshot` (existing) gains, per game, the prices available at snapshot time, the evaluation as issued, and the model version, so the candidates record is reproducible. `users`, `preferences`, `bankrolls`, `bets`, and `model_versions` are new tables in the managed database; Live Record keys migrate forward untouched with an idempotent boot migration, following the v2 pattern.

Jobs: odds ingestion every 5–10 minutes during the slate window; closing-line capture at first pitch; grading on boot and on slate refresh (existing), extended to user bets and CLV.

---

## Appendix A — Verdict engine specification

**Inputs per game.** `p_season_home`, `p_adj_home` (nullable), prices per side per book with timestamps, `gp_home`, `gp_away`, `starters_confirmed`, game status. The user's selected books determine `price_used` (best price among the user's books for the side); "best available" across all books is reported separately as information.

**Derived per side.** `p_eval = p_adj if available else p_season`; `q = implied(price_used)`; `edge = p_eval − q` (points); `ev = p_eval × (decimal − 1) − (1 − p_eval)`; `breakeven = q`; `chance_lose = 1 − p_eval`; `agree = sign(ev_season) == sign(ev_adj)` when both exist.

**Gates (evaluated first).**

| Condition | Result |
|---|---|
| Status is live, final, or postponed | No verdict; pre-game evaluation frozen for grading |
| No price for the side | `INSUFFICIENT_DATA (no_price)`; model chance and fair price still shown |
| `min(gp_home, gp_away) < 30` | `INSUFFICIENT_DATA (early_season)` |
| Price older than 15 minutes | Verdict stands; flag `stale` |
| `p_adj` null (starters unconfirmed) | Verdict stands on `p_season`; flag `starters_unconfirmed`; signal capped at Moderate |
| `min(gp) < 60` | Flag `small_sample`; uncertainty at least Moderate |

**Side verdict (published thresholds, changeable only with a changelog entry).**

| Verdict | Rule |
|---|---|
| `AVOID_AT_THIS_PRICE` | `ev ≤ −0.05` |
| `NO_VALUE` | `ev ≤ 0` or `edge < 0.01` |
| `MARGINAL_VALUE` | `ev > 0` and `edge ≥ 0.01`, but not a candidate; also any side that would be a candidate while `agree` is false (flag `prices_disagree`) |
| `BET_CANDIDATE` | `ev ≥ 0.04` and `edge ≥ 0.03` and (`p_adj` null or `agree`) |

**Game verdict.** The best side by `ev` among candidates and marginals; otherwise `NO_VALUE`, with an `avoid_note` naming any side that is `AVOID_AT_THIS_PRICE`. Insufficient-data gates override. The takeaway names the value side and states when it differs from the lean.

**Signal strength** (only for candidate and marginal). `gap = edge / σ`, with σ a published constant (initially 0.04) revised from live calibration. *Strong*: `gap ≥ 1.0` and `agree` and complete data (starters confirmed, `min(gp) ≥ 60`, price fresh). *Moderate*: `gap ≥ 0.5`, or `gap ≥ 1.0` with one ingredient missing. *Weak*: otherwise. Labels are marked provisional until the bucket has 200 graded candidates.

**Risk.** `volatility`: Lower for prices at −200 or shorter, Higher for +150 or longer, Typical otherwise. `uncertainty`: High if `min(gp) < 60` or `|p_adj − p_season| ≥ 0.05`; Moderate if `min(gp) < 100` or the gap is at least 0.03; Low otherwise.

**Fixtures (must pass before the engine ships).**

| # | Inputs | Expected |
|---|---|---|
| 1 | p 0.58, price −115, gp 126/126, starters confirmed, fresh | edge +4.5, EV +8.4, `BET_CANDIDATE`, gap 1.13 → Strong |
| 2 | LAD p 0.55 at −150; SD p 0.45 at +125 | LAD: edge −5.0, EV −8.3 → `AVOID`; SD: edge +0.6, EV +1.25 → `NO_VALUE`; game `NO_VALUE` with avoid note on LAD |
| 3 | p 0.53, no price | `INSUFFICIENT_DATA (no_price)`; fair −115 shown |
| 4 | p 0.60 at +150 | edge +20.0, EV +50.0, `BET_CANDIDATE`, Strong |
| 5 | p 0.52 at −110 | edge −0.4, EV −0.7, `NO_VALUE` |
| 6 | p 0.58 at −130 | edge +1.5, EV +2.6, `MARGINAL_VALUE`, gap 0.37 → Weak |
| 7 | p_season 0.58, p_adj 0.54, price −115 | evaluated on 0.54: edge +0.5 → `NO_VALUE`; note that the season price alone would have shown value |
| 8 | gp 18/20 | `INSUFFICIENT_DATA (early_season)`; model chance still displayed |
| 9 | fixture 1 with price 40 minutes old | `BET_CANDIDATE` with `stale` flag |
| 10 | fixture 1 with `p_adj` null | `BET_CANDIDATE`, signal capped Moderate, flag `starters_unconfirmed` |

---

## Appendix B — Explanation generator specification

**Inputs.** Both teams' receipts: OBP, SLG, OBP-against, SLG-against, predicted runs scored and allowed per game, Pythagorean strength; the starter blend (starter OBP-against and SLG-against, blend weight, `p_season`, `p_adj`); games played; the evaluation; context items (IL flags for top-five playing-time players, transactions in the last 72 hours, media pulse with item count).

**Component deltas** (for lean side X versus Y): offense = predicted RS/G(X) − RS/G(Y); prevention = RA/G(Y) − RA/G(X); starters = `p_adj − p_season` in points, attributed to the starter blend. Each delta is converted to an approximate win-probability contribution using the fitted runs-per-win slope so that bullets can be ranked by magnitude.

**Templates (priced inputs only).**

- Offense, when |delta| ≥ 0.15 runs per game: "{X}'s offense projects to more runs: {rs_x} per game vs {rs_y} (on-base {obp_x} vs {obp_y}, slugging {slg_x} vs {slg_y})."
- Prevention, when |delta| ≥ 0.15: "{X}'s run prevention is stronger: {ra_x} allowed vs {ra_y}."
- Starters, when |delta| ≥ 1 point: "Tonight's starter {helps/hurts} {X}: {name} holds hitters to a {obpa} on-base average, {better/worse} than {X}'s team rate. With starters, the price moves from {fair_season} to {fair_adj}."
- Counterweight, when a component favors Y: "{Y} has the {better offense / stronger run prevention} ({value} vs {value}), but not by enough to offset {the other component}."
- Sample sentence, always last: "Based on {gp_x} and {gp_y} games this season."

**Candidate and no-value lines.** Candidate: "{Book} has {X} at {price}. The model's fair price is {fair}, so the book is offering better odds than the model thinks the matchup deserves." No value: "{Book} has {X} at {price}, which implies {q}%. The model's fair price is {fair}; the price is worse than fair." Marginal: "...slightly better than fair, but inside the range where the model is often wrong." Avoid: "...much worse than fair."

**Takeaway sentence.** One per game, by verdict, naming the value side and, when it differs from the lean, saying so: "The model leans {lean} ({p}%), but the price is better on {value_side} at {price} — marginal value."

**Context chips.** IL flag (team, player, status), transaction (type, one-line description), media pulse when |score| ≥ 25 (score and item count, opens evidence), and the standing limitations shown when expanded: "Home field: not priced," "Lineups: not priced," "Weather: not priced," "Bullpen: approximated by team rate." Chips are labeled "not in the price" and never appear in the lean list.

**Rules.** Maximum three lean bullets ranked by magnitude, with at most one counterweight. Every number is formatted by the dictionary rules. No template renders without a real value (the v2 desk-note rule). Prohibited words are impossible by construction (the lint runs on templates). If a template's condition is not met and no bullet qualifies, the list reads "The two teams are close on every input the model prices," which is itself a useful explanation.

**Golden tests.** Ten hand-written fixtures covering: a clear favorite on all components; a split (offense favors X, prevention favors Y); a starter that flips the lean; an injury flag on the lean side (must not appear in the lean list); a no-value takeaway where the value side is the underdog; and an early-season game (sample sentence with a small-sample note).

---

## Appendix C — Stake sizing specification

1. Market de-vigged chance for the side: `q_side / (q_side + q_other)` from the same book's two prices.
2. Staking chance: `p_stake = w × p_eval + (1 − w) × q_devig`, with `w` a published constant (initially 0.5) that may only increase by a changelog decision tied to the live record.
3. Full Kelly on the staking chance: `f = (p_stake × b − (1 − p_stake)) / b`, where `b = decimal − 1`. If `f ≤ 0`, no stake.
4. Profile fraction and cap: Conservative ¼, cap 1% (parlay 0.5%); Balanced ½, cap 2% (parlay 1%); Higher variance ¾, cap 3% (parlay 1.5%).
5. Stake = `min(fraction × f, cap) × bankroll`, rounded to the nearest dollar; never shown when `ev ≤ 0` on the model's own chance either.
6. Projection: a 100-bet simulation at the staking chance and the chosen stake fraction, reporting the mean outcome, the share of runs that end down, and the median worst dip. Cached per (chance, price, fraction) triple.

Fixture: model 0.58, prices −115/+105, bankroll $1,000 → de-vigged 52.3%, staking chance 55.2%, full Kelly 3.6%, stakes $9 / $18 / $27; projection at Balanced: about +$57 mean, roughly one in three runs ends down, median worst dip about 15%.

---

## Appendix D — Copy rules

**Tone.** Calm, specific, and short. Second person only for actions the user takes. Numbers before adjectives. Uncertainty stated as a number wherever one exists ("loses 42% of the time," not "risky").

**Required qualifiers.** Every record carries its sample size and since-date. Every price carries its book and its as-of time. Every in-season number carries games played. Every backtest figure sits under the historical banner. Every stake says "paper" until confirmed. Every context chip says "not in the price."

**Prohibited words and patterns** (lint fails the build): lock, guaranteed, free money, can't lose, sure thing, hot, on fire, streak, must-bet, best bet, play of the day, slip of the day, fade, boost, risk-free, bet now, recommended bet, suggested bet, expert, insider, "beats the books" (until the record page itself qualifies the claim), any emoji in product copy, countdown language ("hurry," "before it moves").

**Rewrites of existing strings.**

| Current | New |
|---|---|
| VALUE | Bet candidate |
| INSIDE THE VIG — NO PLAYABLE EDGE | Inside the sportsbook's cut — no value |
| NO VALUE | No value detected |
| HISTORICAL MODE | Season over — showing historical seasons |
| TRACKING SINCE AUG 2026 · SMALL SAMPLE | Tracking since August 2026 · small sample |
| STATISTICAL RESEARCH · NOT WAGERING ADVICE | Research tool, not betting advice. 21+ |
| MODEL SLIP OF THE DAY | (removed from default surfaces) |
| MODEL LIKES NYY · MEDIA PULSE −41 | Model leans New York · news tone is negative (−41, 12 items) — not in the price |
| ½-KELLY PAPER STAKE | Model-sized stake (paper) |
| THRU 126 GP | Through 126 games |
| ADJ −118 · SEASON −132 | With tonight's starters −118 · Season strength −132 |

---

## Appendix E — Analytics and comprehension metrics

Events: `card_expand_why`, `card_expand_numbers`, `tooltip_open(term)`, `calc_expander_open(metric)`, `verdict_filter(value)`, `sort_change`, `record_visit(section)`, `price_checker_used`, `bankroll_setup`, `profile_change`, `stake_logged(paper|real)`, `limit_set`, `cooling_off_on`, `lesson_complete(id)`, `detail_level_change`, `explain_terms_change`, `share_card_created`.

Comprehension measures: a two-question in-product survey after the third session ("In your own words, what does 'fair price' mean?" and "What does 'loses 42% of the time' tell you?") scored by rubric; the share of users who open "Why" at least once in their first week; the share of sessions with a Track Record visit; and the pass-rate awareness check ("roughly how many of today's games were candidates?").

Guardrail metrics: stakes above profile cap (must be zero), dollar figures rendered without a bankroll (must be zero), notifications containing a stake or a price move (must be zero), copy-lint failures in CI (must be zero).

---

## Appendix F — Migration map from v2

| v2 tab or panel | v3 route | Notes |
|---|---|---|
| DESK (SlateRail, Pricer, Edge Finder, BA Paradox, Track Record, Bankroll backtest, Live Record, Screener, Status strip) | `/today` (slate), `/research/teams` (pricer, screener), `/game/{gamePk}` (edge finder as Check a price), `/research/learn` (BA paradox), `/record` (track record, backtest, live record), footer (status) | Redirect `/` to `/today`; keep `/desk` as a redirect for a release |
| PLAYERS | `/research/players` | Restyle in Phase 3 |
| H2H | `/research/matchups` | Team mode reuses the price checker |
| PARLAY | `/parlay` | Model slip of the day removed from default view |
| SEASON | `/research/teams` | Projections, remaining schedule, 2027 refusal state |
| WIRE | `/research/news` | Feeds context chips |
| Keyboard 1–6 | 1–5 for primary destinations; "/" for search | Documented in settings |
| Replit DB keys | Unchanged; new tables for users, preferences, bankrolls, bets, line snapshots, model versions | Idempotent boot migration |

---

*End of document.*
