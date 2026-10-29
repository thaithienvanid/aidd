# Hosts: the extensions-and-marketplace-apps detail

Each row was read at its source on 2026-09-30, and WordPress, Edge, Open VSX, and Google Workspace on 2026-10-22. A host changes its policy without a version number. In Specify, re-read a row's
source when it is more than six months old. Propose a changed row to aidd's `schemas/packs.json` and this file together.

## What each host's review rejects

| Host | Code and permissions | Listing and data | Source |
| --- | --- | --- | --- |
| Chrome Web Store | one narrow, easy-to-understand purpose; the narrowest permissions that work; Manifest V3 only (every remaining MV2 item removed 2026-08-31); no remotely hosted code: no `<script>` outside the package, no `eval` of a fetched string, no interpreter for fetched commands; no obfuscation, minification allowed | a privacy policy link in the dashboard when the item handles user data, and the Limited Use statement | <https://developer.chrome.com/docs/webstore/program-policies/policies> |
| Microsoft Edge Add-ons | one purpose with narrow functionality; no obfuscation | a privacy policy when the extension handles personal data | <https://learn.microsoft.com/en-us/legal/microsoft-edge/extensions/developer-policies> |
| Firefox (AMO) | only the permissions it needs; self-contained, no remote code; no remote new-tab page; never relaxes a page's CSP; the source and build steps for any transpiled or minified code | new extensions since 2025-11-03 declare `data_collection_permissions` (Firefox 140+ desktop, 142+ Android) | <https://extensionworkshop.com/documentation/publish/add-on-policies/> |
| VS Code Marketplace | `vsce package` refuses a detected secret; `.vscodeignore` keeps out what the runtime does not need | a verified publisher proves a domain | <https://code.visualstudio.com/api/working-with-extensions/publishing-extension> |
| Open VSX (VS Code forks such as VSCodium) | the publisher agreement signed; the namespace created before the first publish, and claimed to show as verified | a token per environment, kept as a CI secret | <https://github.com/eclipse/openvsx/wiki/Publishing-Extensions> |
| Shopify App Store | session tokens: an embedded app works without third-party cookies or local storage, in Chrome incognito; restricted scopes such as `read_all_orders` only with a shown need | a demo screencast of onboarding and features (English or English subtitles) | <https://shopify.dev/docs/apps/launch/shopify-app-store/app-store-requirements> |
| Slack Marketplace | no legacy or broad scopes without a clear use case; no joining every public channel on install | landing, support, and privacy pages public, not behind a login; the privacy policy says what is collected, how it is used, and how long it is kept | <https://docs.slack.dev/slack-marketplace/slack-marketplace-app-guidelines-and-requirements> |
| Atlassian Marketplace | every endpoint authenticated; least-privilege scopes; TLS 1.2+ with HSTS of a year; data stored outside Atlassian encrypted at rest; secrets out of source, repositories, and logs; no critical or high vulnerable dependency; no end-of-life Node.js | a security contact; incidents reported through ECOHELP; fixes within the Security Bug Fix Policy | <https://developer.atlassian.com/platform/marketplace/security-requirements/> |
| Teams store | a manifest on a publicly released schema | privacy policy and terms links | <https://learn.microsoft.com/en-us/microsoftteams/platform/concepts/deploy-and-publish/appsource/prepare/teams-store-validation-guidelines> |
| Salesforce AgentExchange (formerly AppExchange) | the managed package scanned with Code Analyzer and the Checkmarx Source Code Scanner; fixable findings fixed, false positives documented | end-to-end testing, test environments, and documentation before submission | <https://developer.salesforce.com/docs/platform/isvforce/guide/security-review-prepare.html> |
| Google Workspace Marketplace | OAuth app verification; a restricted scope (such as Gmail or Drive data) only with a yearly security assessment (CASA) | the app deletes user data on request, which the assessment checks | <https://support.google.com/cloud/answer/13465431> |
| WordPress.org plugin directory | GPL-compatible code; no executable code sent through third-party systems; code (mostly) human readable, no obfuscation | no contact with external servers, and no tracking of users, without explicit consent | <https://developer.wordpress.org/plugins/wordpress-org/detailed-plugin-guidelines/> |

## Reviewer access, money, and AI

| Host | Reviewer access | Money | AI |
| --- | --- | --- | --- |
| Shopify App Store | test credentials that are valid and open the whole feature set | the Billing API or Shopify App Pricing for every charge, accepted, declined, and re-requested on reinstall | — |
| Slack Marketplace | — | — | Slack data never trains an LLM; no consequential decision by AI without human review |
| Teams store | test accounts valid for as long as the app is live, filled with sample data, with step-by-step test notes | commerce links kept out of the privacy policy and terms | AI-generated content within commercial marketplace policy 100.10 |
| Salesforce AgentExchange | test environments configured before submission | — | — |

## The publish credential

VS Code Marketplace: global Azure DevOps Personal Access Tokens are retired on 2026-12-01; publish from CI with
Microsoft Entra ID workload identity (`vsce publish --azure-credential`). Every other host here publishes from its
partner or developer account: keep that account's sign-in behind MFA and out of CI.

## Staged rollout

The Chrome Web Store offers a percentage rollout for an item with over 10,000 users, so an update reaches a share of them first. Use a host's staged rollout where it has one. Source: <https://developer.chrome.com/docs/webstore/update>.
