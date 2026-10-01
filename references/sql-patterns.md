# APPENDIX — SQL patterns

Placeholders: `PROJECT`, `DATASET`, `CUSTOMERID`, dates as `DATE 'YYYY-MM-DD'`. Column names follow the Google Ads transfer schema as of 2026. **Confirm names in `INFORMATION_SCHEMA.COLUMNS` before running**, and check GA4 report columns the same way (they differ by report and connector version).

**1. Inventory: freshness and size per table (metadata only)**
```sql
-- inventory__partitions__v1
SELECT table_name,
       MIN(partition_id)       AS first_partition,
       MAX(partition_id)       AS last_partition,
       SUM(total_rows)         AS total_rows,
       MAX(last_modified_time) AS last_modified
FROM `PROJECT.DATASET.INFORMATION_SCHEMA.PARTITIONS`
WHERE partition_id NOT IN ('__NULL__', '__UNPARTITIONED__')
GROUP BY table_name
ORDER BY table_name;
```

**2. Campaign daily performance with current names**
```sql
-- ads__campaign_daily__v1
WITH campaigns AS (
  SELECT campaign_id,
         ANY_VALUE(campaign_name)                    AS campaign_name,
         ANY_VALUE(campaign_advertising_channel_type) AS channel_type
  FROM `PROJECT.DATASET.ads_Campaign_CUSTOMERID`
  WHERE _DATA_DATE = _LATEST_DATE
  GROUP BY campaign_id
),
stats AS (
  SELECT segments_date AS date, campaign_id,
         SUM(metrics_impressions)         AS impressions,
         SUM(metrics_clicks)              AS clicks,
         SUM(metrics_cost_micros) / 1e6   AS cost,
         SUM(metrics_conversions)         AS conversions,
         SUM(metrics_conversions_value)   AS conv_value
  FROM `PROJECT.DATASET.ads_CampaignBasicStats_CUSTOMERID`
  WHERE _DATA_DATE BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 63 DAY)
                       AND DATE_SUB(CURRENT_DATE(), INTERVAL 4 DAY)  -- skip immature days
  GROUP BY date, campaign_id
)
SELECT s.date, c.campaign_name, c.channel_type,
       s.impressions, s.clicks, s.cost, s.conversions, s.conv_value,
       SAFE_DIVIDE(s.cost, s.clicks)        AS cpc,
       SAFE_DIVIDE(s.conversions, s.clicks) AS cvr,
       SAFE_DIVIDE(s.cost, s.conversions)   AS cpa,
       SAFE_DIVIDE(s.conv_value, s.cost)    AS roas
FROM stats s
LEFT JOIN campaigns c USING (campaign_id)
ORDER BY s.date, c.campaign_name;
```

**3. Search terms with statistically unlikely zero conversions (masked)**
```sql
-- ads__search_terms_zero_conv__v1
-- Window ends 4 days ago; extend the gap for long conversion lags.
WITH base AS (
  SELECT campaign_id,
         LOWER(TRIM(search_term_view_search_term)) AS term,
         SUM(metrics_clicks)            AS clicks,
         SUM(metrics_cost_micros) / 1e6 AS cost,
         SUM(metrics_conversions)       AS conversions
  FROM `PROJECT.DATASET.ads_SearchQueryStats_CUSTOMERID`
  WHERE _DATA_DATE BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 94 DAY)
                       AND DATE_SUB(CURRENT_DATE(), INTERVAL 4 DAY)
  GROUP BY campaign_id, term
),
campaign_cvr AS (
  SELECT campaign_id, SAFE_DIVIDE(SUM(conversions), SUM(clicks)) AS p
  FROM base
  GROUP BY campaign_id
)
SELECT b.campaign_id,
       REGEXP_REPLACE(
         REGEXP_REPLACE(b.term, r'[\w.+-]+@[\w-]+\.[\w.]+', '[email]'),
         r'\d{3,}', '#')                 AS term_masked,
       b.clicks, b.cost, b.conversions,
       c.p                               AS campaign_cvr,
       POW(1 - c.p, b.clicks)            AS p_zero_if_typical
FROM base b
JOIN campaign_cvr c USING (campaign_id)
WHERE b.conversions = 0
  AND c.p > 0
  AND POW(1 - c.p, b.clicks) < 0.05
ORDER BY b.cost DESC;
```

**4. Daily spend anomalies: same-weekday robust z-score**
```sql
-- ads__daily_cost_anomaly__v1
WITH daily AS (
  SELECT segments_date AS date, campaign_id,
         SUM(metrics_cost_micros) / 1e6 AS cost
  FROM `PROJECT.DATASET.ads_CampaignBasicStats_CUSTOMERID`
  WHERE _DATA_DATE >= DATE_SUB(CURRENT_DATE(), INTERVAL 70 DAY)
  GROUP BY date, campaign_id
),
pairs AS (
  SELECT d.date, d.campaign_id, d.cost, h.cost AS hist_cost
  FROM daily d
  JOIN daily h
    ON h.campaign_id = d.campaign_id
   AND h.date BETWEEN DATE_SUB(d.date, INTERVAL 56 DAY) AND DATE_SUB(d.date, INTERVAL 7 DAY)
   AND EXTRACT(DAYOFWEEK FROM h.date) = EXTRACT(DAYOFWEEK FROM d.date)
  WHERE d.date BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 10 DAY)
                   AND DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
),
med AS (
  SELECT date, campaign_id, ANY_VALUE(cost) AS cost,
         APPROX_QUANTILES(hist_cost, 100)[OFFSET(50)] AS median_cost,
         COUNT(*) AS n_hist
  FROM pairs
  GROUP BY date, campaign_id
),
mad AS (
  SELECT p.date, p.campaign_id,
         APPROX_QUANTILES(ABS(p.hist_cost - m.median_cost), 100)[OFFSET(50)] AS mad
  FROM pairs p
  JOIN med m USING (date, campaign_id)
  GROUP BY p.date, p.campaign_id
)
SELECT m.date, m.campaign_id, m.cost, m.median_cost, a.mad, m.n_hist,
       SAFE_DIVIDE(m.cost - m.median_cost, 1.4826 * a.mad) AS robust_z
FROM med m
JOIN mad a USING (date, campaign_id)
WHERE m.n_hist >= 6
ORDER BY ABS(SAFE_DIVIDE(m.cost - m.median_cost, 1.4826 * a.mad)) DESC;
```

**5. CPA change decomposition between two mature periods (log contributions add up)**
```sql
-- ads__cpa_change_decomposition__v1
-- p0 and p1: equal length, weekday-aligned, both past conversion lag.
WITH agg AS (
  SELECT IF(_DATA_DATE >= DATE 'P1_START', 'p1', 'p0') AS period,
         SUM(metrics_clicks)            AS clicks,
         SUM(metrics_cost_micros) / 1e6 AS cost,
         SUM(metrics_conversions)       AS conv
  FROM `PROJECT.DATASET.ads_CampaignBasicStats_CUSTOMERID`
  WHERE _DATA_DATE BETWEEN DATE 'P0_START' AND DATE 'P1_END'
  GROUP BY period
),
k AS (
  SELECT MAX(IF(period = 'p0', SAFE_DIVIDE(cost, clicks), NULL)) AS cpc0,
         MAX(IF(period = 'p1', SAFE_DIVIDE(cost, clicks), NULL)) AS cpc1,
         MAX(IF(period = 'p0', SAFE_DIVIDE(conv, clicks), NULL)) AS cvr0,
         MAX(IF(period = 'p1', SAFE_DIVIDE(conv, clicks), NULL)) AS cvr1
  FROM agg
)
SELECT cpc0, cpc1, cvr0, cvr1,
       SAFE_DIVIDE(cpc0, cvr0)                  AS cpa0,
       SAFE_DIVIDE(cpc1, cvr1)                  AS cpa1,
       LN(cpc1 / cpc0)                          AS log_contrib_cpc,
       -LN(cvr1 / cvr0)                         AS log_contrib_cvr,
       LN(SAFE_DIVIDE(cpc1, cvr1) / SAFE_DIVIDE(cpc0, cvr0)) AS log_change_cpa  -- = sum of contributions
FROM k;
```
Run the same decomposition per campaign, then a mix-vs-rate split, before concluding what drove a blended change.
