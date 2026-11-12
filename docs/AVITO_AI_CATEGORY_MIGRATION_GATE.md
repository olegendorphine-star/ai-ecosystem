# Avito AI category — controlled migration gate

Status: PROPOSAL ONLY. Do not publish or modify `docs/avito-feed.xml`.

## Verified source

- The live API read-only inventory (two successful manual runs on 2026-11-11) selected an AI-labelled category and returned HTTP 200 for its field endpoint.
- The observed allowlisted field names were `AdStatus`, `Address`, `Description`, `Images`, `ListingFee`, `Price`, `PriceList`, `Title`.
- The four active ads' current XML uses `ServiceSubtype=IT, дизайн, тексты`, `ServiceSubspecies=Программирование, настройка CRM`, `Specialty=Программирование`, and `WorkingWithAI=Да`.
- The live report does **not** expose the selected category slug, full schema, accepted enumerated values, or current published category of each ad. Do not infer those.

## Evidence matrix for migration

| XML field | Current value | Proposed value | Confidence / action |
|---|---|---|---|
| Category | Предложение услуг | unchanged pending schema | high confidence existing |
| ServiceType | Деловые услуги | unchanged pending schema | high confidence existing |
| ServiceSubtype | IT, дизайн, тексты | **unknown** | require exact official AI hierarchy |
| ServiceSubspecies | Программирование, настройка CRM | **unknown** | require exact official AI hierarchy |
| Specialty | Программирование | **unknown** | require official allowed values |
| WhatServices | Работа и разработка ИИ, нейронных сетей | **unknown** | verify accepted for AI branch |
| Specialisation | Разработка чат-ботов | **unknown** | verify applicability to all four offers |
| WorkingWithAI | Да | preserve only if supported | confirm published filter |
| PriceList | 5000 / 30000 / 150000 RUB | preserve pending review | field name present, full schema not verified |
| Title, Description, Images | current four distinct titles, same six images | no change yet | baseline and test needed |

## Preconditions before any live category update

1. Capture current published category and AI filter flag for each of the four public listing IDs using documented read-only Avito source or authorized cabinet evidence.
2. Retrieve the full official current XML category template or full schema with allowed enumerations. The whitelisted field-name inventory alone is insufficient.
3. Validate a **separate** candidate feed offline against all required fields and prices.
4. Preserve stable XML IDs and Avito IDs. No duplicate advertisements.
5. Check account's actual tariff and potential category-specific listing fees before proposing a change.
6. Record baseline views, contacts, favorites and ranking for at least a comparable period when available.
7. Obtain separate explicit authorization for a single-card controlled rollout, and verify moderation/import result.
8. Stop on errors or HTTP 429; no automatic retries, charges, messaging, or blanket four-city update.

## Safe next engineering work

- Build an **offline-only** XML audit script that reads `docs/avito-feed.xml` and reports for each city: category path, WorkingWithAI flag, title, number of images and PriceList price tiers. It must not write or send network requests.
- Build a CSV baseline importer from an owner-provided Avito statistics export with strict schema validation, no fabricated zero values, and rate calculations from actual numerators/denominators.
- Do not interpret absence of analytics as zero performance.

## Decision

**NO-GO for production category change yet.** The API confirms that the AI category is discoverable; it does not establish the precise feed fields or current published classification. The risk of moderation/failed import outweighs the unmeasured benefit of a blind migration.
