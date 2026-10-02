# APPENDIX — SQL patterns

Placeholders: `PROJECT`, `DATASET`, `CUSTOMERID`, `ACCOUNT_TZ` (IANA name from the Customer match table), dates as `DATE 'YYYY-MM-DD'`, and the thresholds `MIN_COST` and `MIN_ABS_DEVIATION`. Column names follow the Google Ads transfer schema as of 2026. **Confirm names in `INFORMATION_SCHEMA.COLUMNS` before running**, and check GA4 report columns the same way (they differ by report and connector version). Dry-run each pattern and confirm that the `_DATA_DATE` filter reduces bytes before the first real run.

The patterns assume one account per table. When the Customer snapshot holds several `customer_id` values (A2 item 4), add `AND customer_id = <id>` to every stats and match-table scan, including the `loaded` CTE, and run each pattern once per account with that account's `ACCOUNT_TZ`.

Patterns 2–4 anchor on the `loaded` CTE: the latest `_DATA_DATE` of the stats table they read, looked up in the last 14 days of the account time zone. `mature_through` is 3 days earlier (the immaturity window, A3; subtract the account's lag instead when it is longer, and raise the constant bounds of patterns 2, 3 and 3b by the same number of extra days, or the start of the window is cut off). Conversion windows end at `mature_through`, cost monitoring at `last_loaded`. Each scan also carries a constant `_DATA_DATE` bound, because a bound read from a CTE does not prune partitions. No load in the last 14 days returns no rows: treat that as a pipeline problem.

**1. Inventory: freshness and size per table (metadata only)**
```sql
-- inventory__partitions__v2
-- Purpose: first and last partition, gaps, rows and bytes per table, from metadata only.
-- Owner: Analyst. Inputs: PROJECT, DATASET.
-- Caveats: expected_days and missing_days are meaningful only for day-partitioned tables (YYYYMMDD ids; NULL for
--   hourly, monthly, yearly; an integer-range table whose ids have 8 digits gets meaningless values); first and
--   last partition compare as strings, so check the partitioning type of non-transfer tables. missing_days counts gaps between first and last partition only: judge freshness from
--   last_partition. Rows in __NULL__ and __UNPARTITIONED__ (streaming buffer) count in rows and bytes, not in
--   partitions. Non-partitioned tables show 0 partitions, and so does a partitioned table whose rows are all in
--   __NULL__ or __UNPARTITIONED__; views are not listed here (see 1b). BigQuery refuses this view when it has to
--   read more than about 1,000 tables: on such a dataset uncomment the table_name filter and run the pattern per
--   customer ID or table-name prefix.
-- Last verified: 2026-10-02, logic checked on synthetic rows in BigQuery; not run on a live INFORMATION_SCHEMA.
SELECT table_name,
       MIN(pid)                                             AS first_partition,
       MAX(pid)                                             AS last_partition,
       COUNT(pid)                                           AS partitions,
       DATE_DIFF(MAX(day), MIN(day), DAY) + 1               AS expected_days,
       DATE_DIFF(MAX(day), MIN(day), DAY) + 1 - COUNT(day)  AS missing_days,
       SUM(total_rows)                                      AS total_rows,
       SUM(total_logical_bytes)                             AS total_logical_bytes,
       MAX(last_modified_time)                              AS last_modified
FROM (
  SELECT table_name, total_rows, total_logical_bytes, last_modified_time,
         IF(partition_id IN ('__NULL__', '__UNPARTITIONED__'), NULL, partition_id) AS pid,
         IF(LENGTH(partition_id) = 8, SAFE.PARSE_DATE('%Y%m%d', partition_id), NULL) AS day
  FROM `PROJECT.DATASET.INFORMATION_SCHEMA.PARTITIONS`
  -- WHERE ENDS_WITH(table_name, '_CUSTOMERID')  -- only for a dataset of more than about 1,000 tables
)
GROUP BY table_name
ORDER BY table_name;
```

**1b. Inventory: tables and views with their type**
```sql
-- inventory__tables__v1
-- Purpose: every table and view in the dataset with its type.
-- Owner: Analyst. Inputs: PROJECT, DATASET.
-- Caveats: metadata only; says nothing about freshness (pattern 1).
-- Last verified: 2026-10-02, logic checked on synthetic rows in BigQuery; not run on a live INFORMATION_SCHEMA.
SELECT table_name, table_type, creation_time
FROM `PROJECT.DATASET.INFORMATION_SCHEMA.TABLES`
ORDER BY table_name;
```

**2. Campaign daily performance with current names**
```sql
-- ads__campaign_daily__v2
-- Purpose: daily metrics per campaign for the 60 days ending at mature_through, one row per campaign and day.
-- Owner: Analyst. Inputs: PROJECT, DATASET, CUSTOMERID, ACCOUNT_TZ.
-- Caveats: zeros on a day with day_has_any_data = FALSE are a transfer gap, not zero delivery;
--   a campaign missing from the latest snapshot (or every campaign, when that snapshot is over 14 days old) keeps
--   its ID with a NULL name; conversions are by click date. Zero rows also occur when the load is fresh but no
--   campaign has a row in the window: check pattern 1 to tell that apart from a stale load.
-- Last verified: 2026-10-02, logic checked on synthetic rows in BigQuery; not run on live transfer tables.
WITH loaded AS (
  SELECT DATE_SUB(MAX(_DATA_DATE), INTERVAL 3 DAY) AS mature_through
  FROM `PROJECT.DATASET.ads_CampaignBasicStats_CUSTOMERID`
  WHERE _DATA_DATE >= DATE_SUB(CURRENT_DATE('ACCOUNT_TZ'), INTERVAL 14 DAY)
),
stats AS (
  SELECT _DATA_DATE AS date, campaign_id,
         SUM(metrics_impressions)       AS impressions,
         SUM(metrics_clicks)            AS clicks,
         SUM(metrics_cost_micros) / 1e6 AS cost,
         SUM(metrics_conversions)       AS conversions,
         SUM(metrics_conversions_value) AS conv_value
  FROM `PROJECT.DATASET.ads_CampaignBasicStats_CUSTOMERID`, loaded
  WHERE _DATA_DATE >= DATE_SUB(CURRENT_DATE('ACCOUNT_TZ'), INTERVAL 77 DAY)  -- constant bound: prunes partitions; 77 fits a 3-day lag, add the extra days of a longer one
    AND _DATA_DATE BETWEEN DATE_SUB(mature_through, INTERVAL 59 DAY) AND mature_through
  GROUP BY date, campaign_id
),
spine AS (
  SELECT date
  FROM loaded, UNNEST(GENERATE_DATE_ARRAY(DATE_SUB(mature_through, INTERVAL 59 DAY), mature_through)) AS date
),
names AS (
  SELECT campaign_id,
         ANY_VALUE(campaign_name)                     AS campaign_name,
         ANY_VALUE(campaign_advertising_channel_type) AS channel_type
  FROM `PROJECT.DATASET.ads_Campaign_CUSTOMERID`
  WHERE _DATA_DATE = _LATEST_DATE
    AND _DATA_DATE >= DATE_SUB(CURRENT_DATE('ACCOUNT_TZ'), INTERVAL 14 DAY)  -- constant bound: prunes partitions
  GROUP BY campaign_id
)
SELECT d.date, c.campaign_id, n.campaign_name, n.channel_type,
       d.date IN (SELECT date FROM stats)   AS day_has_any_data,
       COALESCE(s.impressions, 0)           AS impressions,
       COALESCE(s.clicks, 0)                AS clicks,
       COALESCE(s.cost, 0)                  AS cost,
       COALESCE(s.conversions, 0)           AS conversions,
       COALESCE(s.conv_value, 0)            AS conv_value,
       SAFE_DIVIDE(s.cost, s.clicks)        AS cpc,
       SAFE_DIVIDE(s.conversions, s.clicks) AS cvr,
       SAFE_DIVIDE(s.cost, s.conversions)   AS cpa,
       SAFE_DIVIDE(s.conv_value, s.cost)    AS roas
FROM spine d
CROSS JOIN (SELECT DISTINCT campaign_id FROM stats) c
LEFT JOIN stats s ON s.date = d.date AND s.campaign_id = c.campaign_id
LEFT JOIN names n ON n.campaign_id = c.campaign_id
ORDER BY d.date, c.campaign_id;
```

**3. Search terms with statistically unlikely zero conversions (masked)**
```sql
-- ads__search_terms_zero_conv__v2
-- Purpose: zero-conversion search terms whose clicks make zero unlikely at the campaign's own rate. Candidates, not decisions.
-- Owner: Analyst. Inputs: PROJECT, DATASET, CUSTOMERID, ACCOUNT_TZ; MIN_COST = the campaign's target CPA (from the
--   match tables when present, A2, otherwise from the human), or NULL to use each campaign's average CPA over the
--   window. MIN_COST is one floor for every campaign scanned: when targets differ, or some campaigns have none,
--   add a campaign_id filter to base and run it per group sharing a target, or pass NULL.
-- Caveats: 90 days ending at mature_through. Assumes at most one conversion per click: campaigns whose campaign_cvr
--   is outside (0, 1) are not tested (say so, and say when conversions are fractional). False discovery is held at 5%
--   (Benjamini–Hochberg) across the whole family: every term above the impression and cost floors, with or
--   without conversions; terms_tested is the size of that family. Terms under 10 impressions appear only in the 'low-volume terms'
--   row of their campaign. Masking covers emails and digit runs, not names.
-- Last verified: 2026-10-02, logic checked on synthetic rows in BigQuery; not run on live transfer tables.
WITH loaded AS (
  SELECT DATE_SUB(MAX(_DATA_DATE), INTERVAL 3 DAY) AS mature_through
  FROM `PROJECT.DATASET.ads_SearchQueryStats_CUSTOMERID`
  WHERE _DATA_DATE >= DATE_SUB(CURRENT_DATE('ACCOUNT_TZ'), INTERVAL 14 DAY)
),
base AS (
  SELECT campaign_id,
         REGEXP_REPLACE(LOWER(TRIM(search_term_view_search_term)), r'\s+', ' ') AS term,
         SUM(metrics_impressions)       AS impressions,
         SUM(metrics_clicks)            AS clicks,
         SUM(metrics_cost_micros) / 1e6 AS cost,
         SUM(metrics_conversions)       AS conversions
  FROM `PROJECT.DATASET.ads_SearchQueryStats_CUSTOMERID`, loaded
  WHERE _DATA_DATE >= DATE_SUB(CURRENT_DATE('ACCOUNT_TZ'), INTERVAL 107 DAY)  -- constant bound: prunes partitions; 107 fits a 3-day lag, add the extra days of a longer one
    AND _DATA_DATE BETWEEN DATE_SUB(mature_through, INTERVAL 89 DAY) AND mature_through
  GROUP BY campaign_id, term
),
campaign AS (
  SELECT campaign_id,
         SAFE_DIVIDE(SUM(conversions), SUM(clicks)) AS p,        -- baseline, tested term included
         SAFE_DIVIDE(SUM(cost), SUM(conversions))   AS avg_cpa,
         SUM(IF(impressions < 10, impressions, 0))  AS rare_impressions,
         SUM(IF(impressions < 10, clicks, 0))       AS rare_clicks,
         SUM(IF(impressions < 10, cost, 0))         AS rare_cost,
         SUM(IF(impressions < 10, conversions, 0))  AS rare_conversions
  FROM base
  GROUP BY campaign_id
),
tested AS (
  SELECT b.campaign_id, b.term, b.impressions, b.clicks, b.cost, c.p,
         b.conversions,
         IF(b.conversions = 0, POW(1 - c.p, b.clicks), 1) AS p_zero  -- a term with conversions stays in the family with p = 1
  FROM base b
  JOIN campaign c USING (campaign_id)
  WHERE c.p > 0 AND c.p < 1
    AND b.impressions >= 10
    AND b.cost >= COALESCE(MIN_COST, c.avg_cpa)
),
ranked AS (
  SELECT campaign_id, term, impressions, clicks, cost, conversions, p, p_zero,
         COUNT(*) OVER (ORDER BY p_zero) AS k,  -- rank; ties share the highest
         COUNT(*) OVER ()                AS m
  FROM tested
)
SELECT campaign_id,
       FARM_FINGERPRINT(term) AS term_key,
       REGEXP_REPLACE(
         REGEXP_REPLACE(term, r'[^\s@]+@[^\s@]+\.[^\s@]+', '[email]'),
         r'\p{Nd}(?:[\s\p{Z}\p{Pd}.()/]*\p{Nd}){6,}', '[number]') AS term_masked,
       impressions, clicks, cost, 0 AS conversions,
       p AS campaign_cvr, p_zero, m AS terms_tested
FROM ranked
WHERE conversions = 0
  AND k <= (SELECT MAX(k) FROM ranked WHERE p_zero <= k / m * 0.05)
UNION ALL
SELECT campaign_id, NULL, 'low-volume terms',
       rare_impressions, rare_clicks, rare_cost, rare_conversions,
       p, NULL, NULL
FROM campaign
ORDER BY term_masked = 'low-volume terms', cost DESC;
```
`term_key` identifies a term without showing it. Quote `term_masked` only.

**3b. Exact text of chosen search terms (run by the human only)**
```sql
-- ads__search_term_lookup__v1
-- Purpose: exact text for chosen term_key values from pattern 3, for example to build an exact negative.
-- Owner: Analyst drafts it; the human runs it in their own console. Inputs: PROJECT, DATASET, CUSTOMERID,
--   ACCOUNT_TZ; TERM_KEYS = comma-separated term_key values.
-- Caveats: returns unmasked search terms, which may hold personal data. Run it within a few days of pattern 3,
--   or the oldest terms fall out of the window.
-- Last verified: 2026-10-02, logic checked on synthetic rows in BigQuery; not run on live transfer tables.
SELECT DISTINCT campaign_id, FARM_FINGERPRINT(term) AS term_key, term
FROM (
  SELECT campaign_id,
         REGEXP_REPLACE(LOWER(TRIM(search_term_view_search_term)), r'\s+', ' ') AS term
  FROM `PROJECT.DATASET.ads_SearchQueryStats_CUSTOMERID`
  WHERE _DATA_DATE >= DATE_SUB(CURRENT_DATE('ACCOUNT_TZ'), INTERVAL 107 DAY)
)
WHERE FARM_FINGERPRINT(term) IN (TERM_KEYS);
```
The assistant does not run 3b and does not display its output.

**4. Daily spend anomalies: same-weekday robust z-score**
```sql
-- ads__daily_cost_anomaly__v2
-- Purpose: score each campaign's cost on the last 10 loaded days against the same weekday in the prior 8 weeks.
-- Owner: Analyst. Inputs: PROJECT, DATASET, CUSTOMERID, ACCOUNT_TZ; MIN_ABS_DEVIATION = an amount above 0 in
--   account currency, or NULL for the default (1% of average daily account spend over the baseline window).
-- Caveats: a day without a row counts as cost 0 unless the whole account has no rows that day (no_data_loaded).
--   A weekday on which the account has no rows on at least 3 in 4 of its days in the scan is a normally dark
--   weekday: its no-row days count as cost 0, so spend appearing on one is scored against a median of 0. This
--   applies only when the account has rows on more than half of the scan days; an account dark on most days keeps
--   no_data_loaded there and no baseline, so read an insufficient_history row with cost as a possible spike.
--   no_data_loaded, or a last_loaded before yesterday, is a transfer gap or account-wide zero delivery: check
--   pattern 1 or the UI. With zero account spend in the baseline window the default threshold is 0: any non-zero
--   deviation is then critical with a NULL robust_z.
--   Baseline points are loaded same-weekday days since the campaign's first row in the scan; under 6 gives
--   insufficient_history (cost shown, no z). status is a screen: with many campaigns some flags appear by chance (B3.4).
-- Last verified: 2026-10-02, logic checked on synthetic rows in BigQuery; not run on live transfer tables.
WITH loaded AS (
  SELECT MAX(_DATA_DATE) AS last_loaded
  FROM `PROJECT.DATASET.ads_CampaignBasicStats_CUSTOMERID`
  WHERE _DATA_DATE >= DATE_SUB(CURRENT_DATE('ACCOUNT_TZ'), INTERVAL 14 DAY)
),
daily AS (
  SELECT _DATA_DATE AS date, campaign_id,
         SUM(metrics_cost_micros) / 1e6 AS cost
  FROM `PROJECT.DATASET.ads_CampaignBasicStats_CUSTOMERID`, loaded
  WHERE _DATA_DATE >= DATE_SUB(CURRENT_DATE('ACCOUNT_TZ'), INTERVAL 80 DAY)  -- constant bound: prunes partitions
    AND _DATA_DATE BETWEEN DATE_SUB(last_loaded, INTERVAL 65 DAY) AND last_loaded
  GROUP BY date, campaign_id
),
threshold AS (
  SELECT COALESCE(MIN_ABS_DEVIATION, 0.01 * SAFE_DIVIDE(SUM(cost), COUNT(DISTINCT date))) AS min_abs
  FROM daily, loaded
  WHERE date <= DATE_SUB(last_loaded, INTERVAL 10 DAY)
),
campaigns AS (  -- campaigns with spend anywhere in the scan
  SELECT campaign_id, MIN(date) AS first_seen
  FROM daily
  GROUP BY campaign_id
  HAVING SUM(cost) > 0
),
spine AS (  -- has_data FALSE = no rows for the account on a weekday that normally has rows
  SELECT date,
         has_rows OR (COUNTIF(NOT has_rows) OVER wd >= 0.75 * COUNT(*) OVER wd        -- weekday normally dark
                      AND COUNTIF(has_rows) OVER () > 0.5 * COUNT(*) OVER ()) AS has_data  -- and no long outage
  FROM (
    SELECT date, date IN (SELECT date FROM daily) AS has_rows
    FROM loaded, UNNEST(GENERATE_DATE_ARRAY(DATE_SUB(last_loaded, INTERVAL 65 DAY), last_loaded)) AS date
  )
  WINDOW wd AS (PARTITION BY EXTRACT(DAYOFWEEK FROM date))
),
grid AS (
  SELECT s.date, s.has_data, c.campaign_id, COALESCE(d.cost, 0) AS cost
  FROM spine s
  JOIN campaigns c ON s.date >= c.first_seen
  LEFT JOIN daily d ON d.date = s.date AND d.campaign_id = c.campaign_id
),
pairs AS (
  SELECT e.date, e.campaign_id, e.has_data, e.cost, h.cost AS hist_cost
  FROM grid e
  CROSS JOIN loaded
  LEFT JOIN grid h
    ON h.campaign_id = e.campaign_id
   AND h.has_data
   AND h.date BETWEEN DATE_SUB(e.date, INTERVAL 56 DAY) AND DATE_SUB(e.date, INTERVAL 7 DAY)
   AND MOD(DATE_DIFF(e.date, h.date, DAY), 7) = 0
  WHERE e.date >= DATE_SUB(last_loaded, INTERVAL 9 DAY)
),
with_median AS (
  SELECT date, campaign_id, has_data, cost, hist_cost,
         PERCENTILE_CONT(hist_cost, 0.5) OVER (PARTITION BY date, campaign_id) AS median_cost
  FROM pairs
),
with_mad AS (
  SELECT date, campaign_id, has_data, cost, hist_cost, median_cost,
         PERCENTILE_CONT(ABS(hist_cost - median_cost), 0.5) OVER (PARTITION BY date, campaign_id) AS mad
  FROM with_median
),
scored AS (
  SELECT date, campaign_id, has_data, cost, median_cost, mad, min_abs,
         COUNT(hist_cost) AS n_hist,
         IF(has_data AND COUNT(hist_cost) >= 6, cost - median_cost, NULL) AS deviation,
         GREATEST(1.4826 * mad, 0.10 * median_cost, min_abs)             AS scale
  FROM with_mad, threshold
  GROUP BY date, campaign_id, has_data, cost, median_cost, mad, min_abs
)
SELECT date, campaign_id,
       (SELECT last_loaded FROM loaded)    AS last_loaded,
       IF(has_data, cost, NULL)            AS cost,
       median_cost, mad, n_hist, deviation,
       SAFE_DIVIDE(deviation, median_cost) AS rel_deviation,
       SAFE_DIVIDE(deviation, scale)       AS robust_z,
       CASE
         WHEN NOT has_data THEN 'no_data_loaded'
         WHEN n_hist < 6   THEN 'insufficient_history'
         WHEN deviation = 0 THEN 'ok'
         WHEN ABS(deviation) >= GREATEST(3 * scale, 0.25 * median_cost, min_abs) THEN 'critical'
         WHEN ABS(deviation) >= GREATEST(2 * scale, 0.25 * median_cost, min_abs) THEN 'watch'
         ELSE 'ok'
       END AS status
FROM scored
ORDER BY ABS(deviation) DESC, cost DESC;
```
A deviation is material at 25% of the baseline median or more and at least `MIN_ABS_DEVIATION` (B3.4); `critical` and `watch` need both that and |z| ≥ 3 or ≥ 2. Rows with status `insufficient_history` or `no_data_loaded` have no deviation and sort last: read them separately, by cost.

**5. CPA change decomposition between two mature periods (log contributions add up)**
```sql
-- ads__cpa_change_decomposition__v2
-- Purpose: split the CPA change between two periods into a CPC part and a CVR part that add up in logs.
-- Owner: Analyst. Inputs: PROJECT, DATASET, CUSTOMERID, P0_START, P0_END, P1_START, P1_END.
-- Caveats: the periods must not overlap; both past the immaturity window (A3), weekday-aligned, equal length
--   (days0 and days1 count days with data). decomposable = FALSE when either period has zero clicks, cost or
--   conversions: use the logs only when decomposable = TRUE (some may still be non-NULL).
-- Last verified: 2026-10-02, logic checked on synthetic rows in BigQuery; not run on live transfer tables.
WITH agg AS (
  SELECT IF(_DATA_DATE BETWEEN DATE 'P1_START' AND DATE 'P1_END', 'p1', 'p0') AS period,
         COUNT(DISTINCT _DATA_DATE)     AS days,
         SUM(metrics_clicks)            AS clicks,
         SUM(metrics_cost_micros) / 1e6 AS cost,
         SUM(metrics_conversions)       AS conv
  FROM `PROJECT.DATASET.ads_CampaignBasicStats_CUSTOMERID`
  WHERE _DATA_DATE BETWEEN DATE 'P0_START' AND DATE 'P0_END'
     OR _DATA_DATE BETWEEN DATE 'P1_START' AND DATE 'P1_END'
  GROUP BY period
),
k AS (
  SELECT MAX(IF(period = 'p0', days, NULL))   AS days0,   MAX(IF(period = 'p1', days, NULL))   AS days1,
         MAX(IF(period = 'p0', clicks, NULL)) AS clicks0, MAX(IF(period = 'p1', clicks, NULL)) AS clicks1,
         MAX(IF(period = 'p0', cost, NULL))   AS cost0,   MAX(IF(period = 'p1', cost, NULL))   AS cost1,
         MAX(IF(period = 'p0', conv, NULL))   AS conv0,   MAX(IF(period = 'p1', conv, NULL))   AS conv1
  FROM agg
)
SELECT days0, days1, clicks0, clicks1, cost0, cost1, conv0, conv1,
       SAFE_DIVIDE(cost0, clicks0) AS cpc0, SAFE_DIVIDE(cost1, clicks1) AS cpc1,
       SAFE_DIVIDE(conv0, clicks0) AS cvr0, SAFE_DIVIDE(conv1, clicks1) AS cvr1,
       SAFE_DIVIDE(cost0, conv0)   AS cpa0, SAFE_DIVIDE(cost1, conv1)   AS cpa1,
       COALESCE(LEAST(clicks0, clicks1, cost0, cost1, conv0, conv1) > 0, FALSE) AS decomposable,
       SAFE.LN(SAFE_DIVIDE(cost1 * clicks0, clicks1 * cost0))  AS log_contrib_cpc,
       -SAFE.LN(SAFE_DIVIDE(conv1 * clicks0, clicks1 * conv0)) AS log_contrib_cvr,
       SAFE.LN(SAFE_DIVIDE(cost1 * conv0, conv1 * cost0))      AS log_change_cpa  -- = sum of the two contributions
FROM k;
```

**5b. CPA change decomposition per campaign**
```sql
-- ads__cpa_change_decomposition_by_campaign__v1
-- Purpose: pattern 5 for each campaign.
-- Owner: Analyst. Inputs and caveats: as pattern 5. A campaign absent from one period has NULLs there and
--   decomposable = FALSE.
-- Last verified: 2026-10-02, logic checked on synthetic rows in BigQuery; not run on live transfer tables.
WITH agg AS (
  SELECT campaign_id,
         IF(_DATA_DATE BETWEEN DATE 'P1_START' AND DATE 'P1_END', 'p1', 'p0') AS period,
         COUNT(DISTINCT _DATA_DATE)     AS days,
         SUM(metrics_clicks)            AS clicks,
         SUM(metrics_cost_micros) / 1e6 AS cost,
         SUM(metrics_conversions)       AS conv
  FROM `PROJECT.DATASET.ads_CampaignBasicStats_CUSTOMERID`
  WHERE _DATA_DATE BETWEEN DATE 'P0_START' AND DATE 'P0_END'
     OR _DATA_DATE BETWEEN DATE 'P1_START' AND DATE 'P1_END'
  GROUP BY campaign_id, period
),
k AS (
  SELECT campaign_id,
         MAX(IF(period = 'p0', days, NULL))   AS days0,   MAX(IF(period = 'p1', days, NULL))   AS days1,
         MAX(IF(period = 'p0', clicks, NULL)) AS clicks0, MAX(IF(period = 'p1', clicks, NULL)) AS clicks1,
         MAX(IF(period = 'p0', cost, NULL))   AS cost0,   MAX(IF(period = 'p1', cost, NULL))   AS cost1,
         MAX(IF(period = 'p0', conv, NULL))   AS conv0,   MAX(IF(period = 'p1', conv, NULL))   AS conv1
  FROM agg
  GROUP BY campaign_id
)
SELECT campaign_id, days0, days1, clicks0, clicks1, cost0, cost1, conv0, conv1,
       SAFE_DIVIDE(cost0, clicks0) AS cpc0, SAFE_DIVIDE(cost1, clicks1) AS cpc1,
       SAFE_DIVIDE(conv0, clicks0) AS cvr0, SAFE_DIVIDE(conv1, clicks1) AS cvr1,
       SAFE_DIVIDE(cost0, conv0)   AS cpa0, SAFE_DIVIDE(cost1, conv1)   AS cpa1,
       COALESCE(LEAST(clicks0, clicks1, cost0, cost1, conv0, conv1) > 0, FALSE) AS decomposable,
       SAFE.LN(SAFE_DIVIDE(cost1 * clicks0, clicks1 * cost0))  AS log_contrib_cpc,
       -SAFE.LN(SAFE_DIVIDE(conv1 * clicks0, clicks1 * conv0)) AS log_contrib_cvr,
       SAFE.LN(SAFE_DIVIDE(cost1 * conv0, conv1 * cost0))      AS log_change_cpa
FROM k
ORDER BY GREATEST(COALESCE(cost0, 0), COALESCE(cost1, 0)) DESC;
```
Run 5b, then a mix-vs-rate split, before concluding what drove a blended change.
