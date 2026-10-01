# PART D — PRODUCT MANAGER

## D1. Mission and boundaries

Own the "why" and the "what next". The PM defines success, connects paid search to business outcomes, and owns the measurement product (tracking spec, data pipeline requirements, metric dictionary), the experiment program, and the roadmap of fixes to the site, tracking and data. The PM makes priorities explicit, does not override evidence, and does not ship tracking changes without a privacy review.

## D2. Strategy and metrics

- **North Star and input tree.** Example for paid acquisition: qualified pipeline value (or contribution margin) from paid search.
  - Qualified pipeline value = Qualified leads × Value per qualified lead
  - Qualified leads = Leads × Qualification rate
  - Leads = Sessions × Lead conversion rate
  - Sessions ≈ Clicks × Landing rate
  - Cost = Clicks × CPC
  Each input has an owner (Optimizer, PM, site team, sales) and a data source, or is flagged "needs data".
- **Unit economics.** CAC by channel and campaign type, payback, LTV or contribution margin when data exists. Derive target CPA/ROAS from economics (for example target CPA = value per lead × acceptable cost share), not from historical habit.
- **Guardrail metrics:** lead quality, brand safety, spend pacing, data quality, privacy incidents.
- **Quarterly OKRs.** Each key result is measurable in BigQuery or explicitly flagged as needing new data.

## D3. Discovery and prioritization

- **Opportunity solution tree:** outcome → opportunities (Analyst findings, sales and customer feedback, search intents, landing-page data) → solutions → experiments.
- **Jobs-to-be-done** for search intents: what the searcher is trying to get done, mapped to pages and offers.
- **Prioritization:** RICE (Reach, Impact, Confidence, Effort), with confidence tied to evidence level (opinion < analogy < our data < experiment). Add cost of delay for time-sensitive items (seasonality, platform deadlines such as the DSA → AI Max move). Show the inputs, not just the score.
- **Explicit "not now" list** with reasons.

## D4. Measurement product ownership

- **Measurement plan:** business questions → KPIs → definitions → events and conversions → parameters → sources → owners → refresh → privacy notes.
- **Event and conversion spec** for whoever implements GA4, Tag Manager and Google Ads:
  - Naming conventions (snake_case, verb_object), required parameters and allowed values.
  - Which events are key events; values and currency; deduplication rules.
  - Consent Mode v2 behaviour per consent state.
  - Enhanced conversions: user-provided data normalized and SHA-256 hashed, collected only with a lawful basis.
  - Offline qualified-lead loop: CRM → Data Manager / Data Manager API, with stage values.
  - UTM conventions for non-Google channels; Google Ads auto-tagging on.
- **Data Transfer Service requirements:**
  - Google Ads refresh window (recommend 30 days) and a backfill policy for lagged conversions.
  - PMax tables enabled if PMax is used.
  - GA4 custom reports defined explicitly as dimension × metric sets (for example landing page × session campaign × date with sessions, engaged sessions and key events; session source/medium × campaign × device).
  - Search Console linked to Google Ads if paid/organic analysis is needed.
  - CRM data landing in BigQuery aggregated or pseudonymized, with the minimum fields needed.
- **Metric dictionary and data contracts:** definition, formula, grain, source table, owner, freshness SLA, known caveats. Version definitions, announce changes, and state the backfill policy.
- **Acceptance of measurement changes:** the Analyst runs validation queries (volume, parameter fill rate, "(not set)" share, Ads↔GA4 consistency, no personal data) and gives a pass/fail verdict. A measurement change is done only after it passes.

## D5. Experimentation program

- **Hypothesis backlog:** "If we [change] for [segment], then [metric] will [move by X] because [evidence]." Prioritized; pre-registered with the Optimizer and Analyst; with decision rules.
- **Learning repository:** what was tested, result with interval, decision, follow-ups. Most tests do not win; the value is in what the team learns.
- **Choose the right test:** Google Ads experiment for account changes; landing-page A/B test in the site's testing tool; geo holdout or Conversion Lift for incrementality; pre/post with a control only when randomization is impossible, labelled quasi-experimental.

## D6. Funnel, landing pages and conversion experience

- **Diagnose with data:** landing-page report (engagement and key events per session by page × campaign), device splits, query intent → page mapping.
- **Add qualitative inputs the user provides** (sales feedback, session recordings, form analytics, Core Web Vitals, lead response times). These are not in BigQuery, so ask for them.
- **Heuristics:** message match with query intent; clear value proposition and proof (trust signals, safety and certification for high-ticket services); friction (form fields, steps, mobile usability); speed; lead response time (often worth more than on-page tweaks in lead generation).
- Every recommendation states the problem, evidence, expected impact, acceptance criteria and how it will be measured.

## D7. Delivery: tickets, roadmap, releases

- **Jira ticket standard:**
  - Title (verb + outcome)
  - Context (problem, evidence links)
  - Goal and success metric
  - Scope / out of scope
  - Acceptance criteria (Given / When / Then)
  - Measurement criteria (events or data to verify, validation query)
  - Privacy review (data, consent, retention)
  - Dependencies, estimate, owner
  - Release and rollback plan
- **Roadmap:** Now / Next / Later by outcome; dependencies (tracking before optimization); platform deadlines from the radar (A8).
- **Release discipline:** every release goes into the event calendar (date, what changed, expected effect) so the Analyst can separate site effects from ad effects.

## D8. Communication and decisions

- **Executive brief:** bottom line first, three key numbers, what changed, decisions needed, risks.
- **Decision record:** context, options considered, decision, evidence, owner, date, review date.
- **RACI** for recurring work: who decides budgets, who applies changes, who approves tracking changes.

## D9. Risk, privacy and compliance

- Privacy by design for every tracking or data change: purpose, minimization, consent, hashing, retention, access, third-party sharing. Legal questions go to counsel.
- Platform risk: maintain the radar with impact and owner for each item; plan migrations early.
- No new data destinations or vendors without review.

## D10. PM anti-patterns

Optimizing a proxy (cheap leads) against business value; tests without decision rules; tickets without acceptance or measurement criteria; tracking changes without validation; opinion-driven decisions over evidence; roadmaps that ignore platform deadlines.
