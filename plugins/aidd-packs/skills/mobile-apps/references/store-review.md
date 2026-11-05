# Store review: the rejection causes and the Notes for Review

Load this when a Spec ships to the App Store or Google Play, or when a submission comes back rejected. The rules are the pack's standards. The section numbers are the App Review Guidelines of 2026-06-08.

## The common causes, and the test that prevents each

Apple reports that over 40% of unresolved issues fall under 2.1 App Completeness: crashes, placeholder content, and incomplete information. Most causes below are caught before submission by a test the pack names.

| Cause | Rule | Prevented by |
| --- | --- | --- |
| A crash or a broken flow on the reviewer's device | Apple 2.1(a); the Play pre-launch report | UI tests on the OS matrix |
| Placeholder text, an empty page, a dead link, no support or privacy policy link | Apple 2.1(a), 5.1.1(i) | Review readiness smoke |
| No demo account, expired credentials, a one-time code, or the back end off | Apple 2.1(a); Play sign-in details (reusable, in English, valid everywhere) | Review readiness smoke |
| A new feature not described in the Notes for Review, or a hidden one | Apple 2.3.1(a) | the Notes template below |
| A purpose string that does not say why, or data access the feature does not need | Apple 5.1.1(ii) to (iv); Play permissions policy | Sensitive permission allow-list |
| A required-reason API without an approved reason (ITMS-91053 on upload) | Apple privacy manifest rules | Required-reason API declarations |
| App Privacy or Data safety that misses an SDK's collection | Apple App Privacy details; Play Data safety | SDK inventory against declarations |
| Account creation without in-app deletion, or no web deletion link on Play | Apple 5.1.1(v); Play account deletion | Account deletion end to end |
| A target API or SDK below the store's dated minimum | Play target API level; App Store Connect upload requirements | Store minimum SDK and target levels |
| Digital goods sold outside in-app purchase or Play Billing without an exception | Apple 3.1.1, 3.1.3; Play Payments | a named exception in the Spec |
| An external purchase link or another billing system used where the storefront does not allow it | Apple 3.1.1(a) on the US storefront; the EU alternative terms under the DMA; Japan's MSCA; Play's external offers and alternative billing programs | the storefront and its rule named in the Spec |
| A social login without an equivalent private option | Apple 4.8 | a UI test of each login |
| User-generated content without filter, report, block, and contact | Apple 1.2 | a UI test of each control |
| Third-party analytics or ads in a kids' app beyond what is allowed | Apple 1.3; Play Families | SDK inventory against declarations |
| Personal data sent to a third-party AI without disclosure and consent | Apple 5.1.2(i) | a consent-gate UI test |
| A web page in a wrapper, or one of many near-identical apps | Apple 4.2, 4.3 | product review in Plan |
| A regulated service submitted by a person, not the legal entity | Apple 5.1.1(ix) | the account check at Entry |
| No verified trader status for the EU storefront (an app without it has been removed since 2025-02-17) | the Digital Services Act; App Store Connect | the account check at Entry |

## On a rejection

Reply in App Store Connect or appeal through Play Console with the rule, what changed, and where the reviewer sees it. A rejection that shows a missed rule is a Learn item. Add the test that would have caught it to this pack's tests or the project's.

## Notes for Review template

Keep it in the repository beside the store metadata. Paste it into App Review Information (Apple), and into Sign-in details plus the release notes (Play). Put no real secret in the file: the credentials come from the team's secret store at submission.

```text
What changed in this version
- <feature>: <what it does>, <where to find it: screen, tab, or menu path>.
- <feature>: ...

Sign-in
- Demo account: <username> / <password from the secret store>, reusable, no one-time code, valid in every region.
- It holds: <paid or unlocked content, sample data, the roles to see>.
- The back end is live for review until <date>.

To reach each new feature
1. <step>
2. <step>

Purchases
- In-app purchases in this version: <product ids>, each visible at <path>.
- Any other payment: <the 3.1.3 case or Play exemption, and why>.

Data and permissions
- New permissions: <permission>, asked at <moment>, because <reason>.
- Data sent to third parties, AI services included: <what, to whom, the consent screen>.

Hardware, region, or setup the reviewer needs
- <device, QR code as a static URL, sample file, or "none">.

Contact during review: <name, phone, email>.
```
