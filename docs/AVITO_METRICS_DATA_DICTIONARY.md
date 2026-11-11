# Avito daily metrics — data dictionary

The companion CSV is an intake template for manual export/copy from the owner's Avito Pro account. It does not connect to Avito or perform API requests.

## Grain
One row = one Avito listing for one calendar day. Use the immutable Avito listing ID, not the XML feed ID. Record all counts as non-negative integers and spend/revenue as RUB decimal amounts.

## Fields
- `date`: local date shown by Avito account, YYYY-MM-DD.
- `ad_id`: Avito public listing ID. Never place private account identifiers here.
- `city`, `category`: listing's actual city and category as shown in the cabinet.
- `impressions`: impressions in search/recommendations, only if the cabinet exposes this exact metric. Do not substitute search position or views.
- `views`: listing opens/views.
- `contacts`: contacts as Avito defines them for the selected report (chat/phone actions). Preserve the report definition.
- `favorites`: adds to favorites.
- `ad_spend_rub`: actual accrued spend for that listing and day; use 0 only when the report confirms zero.
- `qualified_leads`: manually classified relevant buyer inquiries, based on a fixed qualification rule.
- `proposals_sent`: commercial proposals/estimates sent.
- `deals`: confirmed paid deals attributable to the listing.
- `revenue_rub`: recognized revenue from those deals, not quoted deal value.
- `notes`: moderation, downtime, campaign changes, price changes, missing data or other confounders.

## Derived metrics
- CTR = views / impressions. Only calculate when impressions > 0 and both metrics cover the same scope.
- View-to-contact rate = contacts / views. Do not calculate when views = 0.
- Contact qualification rate = qualified_leads / contacts.
- Lead-to-deal rate = deals / qualified_leads.
- Cost per contact = ad_spend_rub / contacts.
- Cost per qualified lead = ad_spend_rub / qualified_leads.
- Revenue per spend (ROAS) = revenue_rub / ad_spend_rub when spend > 0.
- Profitability/ROMI requires delivery costs, API/subscription costs and gross margin; do not infer it from revenue alone.

## Data quality rules
1. Never treat blank as zero. Blank means not supplied/not available; zero means measured zero.
2. Keep organic and paid traffic separate if Avito provides a split. If not, label the metric as blended.
3. Do not add daily cumulative 7/30-day rolling statistics to daily rows.
4. Do not aggregate rates by averaging row percentages. Aggregate numerators and denominators first.
5. Keep a change log for title, description, image order, category, price, promotion and moderation.
6. Four city cards are not a randomized A/B test: city demand and offer differ.
7. Require sufficient observations before drawing conclusions. A handful of impressions or contacts is not evidence of a reliable lift.

