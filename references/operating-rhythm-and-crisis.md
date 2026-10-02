# PART E — Operating rhythm and crisis protocol

## E1. Operating rhythm

This is the single cadence table. Parts B and C refer here instead of repeating frequencies.

| Cadence | Analyst | Optimizer | PM |
|---|---|---|---|
| Daily (if data allows) | Alert triage | Review alerts, containment if needed | Informed on SEV1–2 only |
| Weekly | Health check memo, finding cards; search-term audit (weekly for accounts heavy in broad match, AI Max or PMax, otherwise every two weeks) | Change set, negatives from the latest audit, pacing | Priorities, unblock tracking and site issues |
| Every two weeks | Experiment monitoring (no peeking decisions) | Bidding target review (change a target only when its evaluation window, C4.10, has closed) | Backlog grooming |
| Monthly | Business review, post-change evaluations, AI Max and PMax audit | Structure, assets, budget reallocation, experiment plan | Roadmap update, decision log review |
| Quarterly | Data Map refresh, incrementality calibration | Full account audit | OKRs, measurement plan review, platform radar review |

## E2. Crisis protocol

Any agent or the user can start the crisis protocol, and meeting a trigger starts it. It is active from step 1: routine work pauses and answers stay short: role speaking, status, impact, data complete through, what is known and what is not, what the human must do now. This short format replaces the A6 format until the protocol is stood down or the crisis is closed. Step 2 either stands the protocol down or confirms the crisis; step 3 classifies it and assigns the severity. Do not run the full inventory while the protocol is active: run only the checks the affected tables need.

**Triggers** (defaults; the user can set different thresholds). `[BigQuery]` = detectable from the data; `[human]` = only the human can report it:
- Spend `[BigQuery]`: daily campaign or account spend that deviates materially (B3.4) and either has robust |z| ≥ 3 (a spike or a collapse, as in B3.4) or is above 150% of expected, where expected is the same-weekday median of the last 6–8 weeks, or the daily plan if the user gave one. When several campaigns are scored for the day, a campaign's z counts only if B3.4 reports the flag as critical (it survives the false-discovery step). A campaign with fewer than 6 baseline points and no daily plan has no expected value: list it, do not trigger on it; with a plan, apply the 150% test and judge materiality against the plan. `[human]`: budget exhausted unusually early (intraday data is not in the transfer).
- Conversions `[BigQuery]`: zero conversions, or a drop of 50% or more against expected (the same-weekday median of the last 6–8 weeks), for 2+ days, with clicks within 25% of their own expected value, in campaigns that normally convert (expected of at least 5 conversions a day; judge smaller campaigns at account level). Measure it on days past the immaturity window (A3), or on conversions by conversion date where the transfer has that metric. Inside the immaturity window a shortfall in click-date conversions is expected: treat it as a watch item that starts the tracking checks in B3.11 (GA4 sessions and key events are not delayed by conversion lag), not as a trigger.
- Tracking `[BigQuery]`: GA4 `google / cpc` sessions ÷ Ads clicks more than 30% below its 28-day median for 2+ days; `google / cpc` key events (spike or vanish) or the "(not set)" share with robust |z| ≥ 3 against the same-weekday median of the last 6–8 weeks (B3.4 method) and at least 25% away from that median, for 2+ days. Key events count only where at least 5 a day are expected. `[human]`: an outage of the site, a landing page, a tag or a conversion upload reported by the human while ads are spending; step 2 confirms it on the human's report.
- Data pipeline `[BigQuery]`: a transfer missing for more than one day, schema change breaking key metrics.
- Account `[human]`: mass ad disapprovals, suspended account or billing issue (reported by the human).
- Privacy: personal data in page URLs, event or form parameters, GA4 dimensions or uploaded data `[BigQuery]` (personal data that searchers typed into search terms is masked under A5 and is not a trigger); unexpected dataset access, or data sent to an unapproved destination `[human]`.

**Severity:** SEV1 — money or personal data actively at risk; SEV2 — measurement or delivery broken, bounded loss; SEV3 — degradation to fix in the normal cycle: after step 3 record it as a finding and close the crisis. Steps 4–8 are skipped, no post-mortem is needed, and routine work and the A6 format resume.

**Steps**
1. **Record:** what, since when, how much, which table and period.
2. **Rule out artefacts:** transfer delay, lag, restatement, schema change. If the anomaly is only lag, restatement or a transfer delay of up to one day, or if after these checks no trigger is met and the human has reported no `[human]` trigger, or if the human confirms that the deviation is the intended effect of a change they applied or announced (change log, calendar, stated plan), stand the protocol down: report it as a watch item and return to routine work and the A6 format. A transfer missing for more than one day or a schema change that breaks key metrics is the data pipeline trigger itself: the crisis is confirmed, continue at step 3. Otherwise the crisis is confirmed.
3. **Classify:** real performance problem / measurement problem / data pipeline problem / account problem / privacy incident, and assign the severity (provisional: revise it after step 4 if the impact estimate changes it).
4. **Estimate impact:** money and conversions lost so far and per day at the current rate.
5. **Contain**, only after step 2 has confirmed the crisis and step 3 has classified it (Optimizer drafts, human applies): reversible actions first (pause, budget cap or exclusion for a performance problem; data exclusion for a tracking outage; a backfill request for a pipeline gap; the list of what the human must fix or appeal for an account problem; a privacy incident follows the reversed order below); irreversible actions only after explicit confirmation.
6. **Find the cause:** Analyst investigates the data; the human reports account and site changes.
7. **Recover and verify:** queries confirming the metric is back to normal, allowing for data delay. A SEV1 or SEV2 crisis is closed when these checks pass and the human confirms; routine work and the A6 format then resume.
8. **Post-mortem** (PM), after a SEV1 or SEV2 crisis is closed: timeline, cause, why it was not caught earlier, new monitor or threshold, decision record.

**Privacy incidents take top priority and reverse the order:** first the human stops the flow and limits access to the data (the PM leads and says exactly what to switch off; the Optimizer supports when an account setting is involved), then investigate.

**Roles:** Analyst leads detection and diagnosis; Optimizer leads containment; PM leads communication, privacy handling and the post-mortem.
