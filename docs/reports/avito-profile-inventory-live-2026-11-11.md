# Avito API read-only inventory — verified live run

- Run: https://github.com/olegendorphine-star/ai-ecosystem/actions/runs/43043602081
- Job: live_readonly, completed successfully on 2026-11-11 at approximately 14:58 UTC.
- Source branch: main, commit 51057a6b2996def56d99cff71cca27607f6a3798.
- Authorization: manual workflow_dispatch, approve_readonly=true.
- Scope: read-only, no writes or payments.

## Observed redacted result

```json
{
  "oauth_http": 200,
  "oauth_ok": true,
  "autoload_enabled": true,
  "http": {
    "account": 200,
    "active_items": 200,
    "autoload_profile": 200,
    "category_tree": 200
  },
  "items": {
    "active_items_first_page_count": 4,
    "moscow_active": true,
    "petersburg_active_first_page": true
  },
  "category_leaf_discovered": true,
  "category_fields_http": 200,
  "category_fields_observed": [
    "AdStatus", "Address", "Description", "Images",
    "ListingFee", "Price", "PriceList", "Title"
  ],
  "pricelist_observed_in_fields": true,
  "writes": 0,
  "messages_read": 0,
  "messages_sent": 0,
  "charges_rub": 0
}
```

## Interpretation

- The Avito OAuth connection, active-item endpoint, autoload profile and category-tree endpoint all responded successfully.
- Four items appeared on the first active-items page; the inventory explicitly identified the Moscow and St. Petersburg items as active. The separate latest live-status report already verifies four active items across all target cities.
- The category field endpoint returned the eight whitelisted field names listed above, including PriceList.
- **This does not confirm the new category «ИИ-решения, нейросети».** The run used main's older category selection that prioritizes programming/CRM. The revised AI-category priority exists only in PR #180.
- The report contains no impressions, CTR, search ranking, qualified contacts, leads, sales or paid promotion performance. Those must be sourced separately.
- Do not run the live API job repeatedly. A new live check is justified only when the updated category discovery has been reviewed and merged, and only after explicit authorization.
- HTTP 429 must not be retried.

## Next steps

1. Review PR #180 and merge only the safe read-only code/test/docs changes.
2. After merge, a **single separately authorized** live inventory can check whether the dedicated AI category is discoverable and whether its allowed fields are exposed.
3. Obtain real listing performance statistics through authorized cabinet export or documented read-only endpoint; do not guess numbers.
4. Keep production XML, category, prices, paid services and messages unchanged until the evidence supports a controlled experiment.
