# Avito: acquisition of real promotion statistics

Status 2026-11-12: the offline validator and per-listing funnel are merged into main (`tools/avito_offline_metrics.py`). **No actual Avito statistics have yet been ingested.**

## Data source decision

1. **Preferred**: authorized Avito Pro / Avito account export for a fixed date range (7 and 30 days), one row per ad per calendar day. Use the canonical `docs/templates/avito-daily-metrics-template.csv` schema.
2. **Alternative**: documented read-only official Avito statistics API, **only if** the actual account's permission and method are verified. Do not guess an endpoint or log response bodies.
3. **Fallback**: manually entered verified values from the owner's cabinet. Preserve original export and evidence outside public repository if it contains personal data.

Do not scrape a private cabinet through anti-bot mechanisms, infer views from public listing pages, or treat missing values as zero.

## Four listings to match

| City | Public Avito ID |
|---|---|
| Москва | 8347570435 |
| Санкт-Петербург | 8477159401 |
| Сургут | 8531755111 |
| Чита | 8414224003 |

The four IDs are already used by the offline validator; confirm their current active status when acquiring metrics. These are listing IDs, not account IDs.

## Import and validation

Run offline:

```sh
python3 tools/avito_offline_metrics.py path/to/verified-avito-daily.csv
```

- Reject unknown listing IDs, duplicate listing/date, negative/non-finite amounts, malformed dates and mismatched city.
- Empty fields are unknown, not zero. Rates with incomplete numerator/denominator coverage are null.
- If the source gives only cumulative period totals, do **not** expand or divide them into invented daily values. First add a separate period-level import schema and tests.
- Keep category and notes from source; do not claim XML category equals actual published category.
- Keep raw files with account/contact information out of public GitHub and Actions logs.

## First evidence-backed report

- Coverage: observed days per listing, missing metrics and definition of contacts.
- Funnel: impressions → views → contacts → qualified leads → deals.
- Economics: spend → cost/contact → cost/qualified lead → revenue/spend, only with measured inputs.
- Timeline of title/category/image/moderation changes.
- No causal claim from simple pre/post comparison without accounting for weekday, seasonality, promotion and changing demand.

## Blockers and decision

- The official availability/authorization of an Avito statistics endpoint has not been confirmed in this project.
- No verified 7/30-day per-listing export has been ingested.
- Therefore: **do not announce CTR uplift, leads, revenue, or optimal paid promotion.**
- Continue offline engineering and ask for the minimal necessary read-only data source before any category migration.
