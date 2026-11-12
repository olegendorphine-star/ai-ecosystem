# Project health repair — 12 November 2026

The fifth reviewed Avito listing was already in production XML. The old
four-record checks stopped the API monitor before OAuth and reported the missing
OAuth result as false. The monitor now accepts the four protected core records
and the exact reviewed fifth listing, rejects unknown/duplicate/paid additions,
and reports skipped checks separately from actual OAuth failures.

The public feed bridge and authenticated monitor share validation. Historical
rollout tests protect the original four records; new production tests verify
all five records and preservation of the original content. Autoload reports
still distinguish the original four-listing SEO cohort from any new publication.
No fifth-listing publication is inferred from its presence in XML.

Three archived FL workflows had duplicate `if` keys. The duplicate keys were
removed while preserving `if: false`; archived write operations remain disabled.
All workflows are now checked for duplicate mapping keys in offline CI.

Wordstat GetRegionsTree now omits the legacy folder override, like the working
GetTop request. This bridge uses a service-account API key; Search API resolves
its folder when the field is absent. No authentication permissions are widened.
No retries, paid calls, quotas or budget limits are changed.

Official auth reference:
https://aistudio.yandex.ru/ru/docs/ai-studio/api-ref/authentication

Production XML, images, prices, advertisements and customer messages are unchanged
by this repair. Live Avito and Wordstat acceptance is recorded in the private
Google Drive project map after release. Platform requirements for real photos
and identity verification are not software failures and cannot be resolved by
replacing identity evidence with synthetic content.
