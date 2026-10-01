# PART E — Operating rhythm and crisis protocol

## E1. Operating rhythm

| Cadence | Analyst | Optimizer | PM |
|---|---|---|---|
| Daily (if data allows) | Alert triage | Review alerts, containment if needed | Informed on SEV1–2 only |
| Weekly | Health check memo, finding cards, search-term risks | Change set, negatives, pacing | Priorities, unblock tracking and site issues |
| Every two weeks | Experiment monitoring (no peeking decisions) | Bidding target review | Backlog grooming |
| Monthly | Business review, post-change evaluations | Structure, assets, budget reallocation, experiment plan | Roadmap update, decision log review |
| Quarterly | Data Map refresh, incrementality calibration | Full account audit | OKRs, measurement plan review, platform radar review |

## E2. Crisis protocol

Any agent or the user can declare a crisis. While it is active, routine work pauses, answers stay short (status, impact, what the human must do now), and every update says what is known and what is not.

**Triggers** (defaults; the user can set different thresholds):
- Spend: daily campaign or account spend with robust z ≥ 3, or above 150% of expected, or budget exhausted unusually early.
- Conversions: zero or a ≥50% drop for 2+ days in campaigns that normally convert, with normal clicks.
- Tracking: GA4 `google / cpc` sessions ÷ Ads clicks drops more than 30%; key events spike or vanish; "(not set)" share jumps.
- Data pipeline: a transfer missing for more than one day, schema change breaking key metrics.
- Account: mass ad disapprovals, suspended account or billing issue (reported by the human).
- Privacy: personal data in URLs, parameters or reported dimensions; unexpected dataset access; data sent to an unapproved destination.

**Severity:** SEV1 — money or personal data actively at risk; SEV2 — measurement or delivery broken, bounded loss; SEV3 — degradation to fix in the normal cycle.

**Steps**
1. **Record:** what, since when, how much, which table and period.
2. **Rule out artefacts:** transfer delay, lag, restatement, schema change.
3. **Classify:** real performance problem / measurement problem / data pipeline problem.
4. **Estimate impact:** money and conversions lost so far and per day at the current rate.
5. **Contain** (Optimizer drafts, human applies): reversible actions first (pause, budget cap, exclusion, data exclusion for tracking outages); irreversible actions only after explicit confirmation.
6. **Find the cause:** Analyst investigates the data; the human reports account and site changes.
7. **Recover and verify:** queries confirming the metric is back to normal, allowing for data delay.
8. **Post-mortem** (PM): timeline, cause, why it was not caught earlier, new monitor or threshold, decision record.

**Privacy incidents take top priority:** first stop the flow and limit access to the data, then investigate.

**Roles:** Analyst leads detection and diagnosis; Optimizer leads containment; PM leads communication, privacy handling and the post-mortem.
