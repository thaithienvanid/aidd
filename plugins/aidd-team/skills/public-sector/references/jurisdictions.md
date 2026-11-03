# Jurisdictions: the public-sector detail outside US federal security

Load this when a Spec serves a public body outside the US federal government, or when it signs in the public. The pack
holds the US federal and defense rules. This file names what other governments ask for, so the Spec can name the control
set it maps to. A row marked "check at source" has a date that was not confirmed at its primary source on 2026-10-22, so
read the source in Specify before the Spec relies on it. Propose a changed row to aidd's `schemas/packs.json` and this
file together.

## European Union

| Rule | What the change does | Dates |
| --- | --- | --- |
| Web Accessibility Directive (EU) 2016/2102 | A public body's website or app meets EN 301 549 and publishes an accessibility statement with a way to report a barrier. | in force |
| eIDAS 2, Regulation (EU) 2024/1183 | A public service that asks for strong identification accepts the EU Digital Identity Wallet, and picks its assurance level (low, substantial, high). | wallets and their acceptance follow the implementing acts: check at source |
| NIS2, Directive (EU) 2022/2555 | A central government entity is in scope. Its incident clocks are `aidd-team:incident-response`'s. | in force |
| Interoperable Europe Act, Regulation (EU) 2024/903 | A new binding requirement for a cross-border public service gets an interoperability assessment. | check at source |
| Open Data Directive (EU) 2019/1024, with the high-value datasets act (EU) 2023/138 | Public data is published free, machine-readable, and through an API where the act names it. | in force |

## United Kingdom

- The GDS Service Standard and the Technology Code of Practice judge a central government service.
- The NCSC's Cyber Assessment Framework sets the security outcomes, and Cyber Essentials is a common contract condition.
- The Public Sector Bodies Accessibility Regulations 2018 ask for WCAG and an accessibility statement.
- Data protection follows the UK GDPR as amended in 2025 (`aidd-team:privacy-by-default`).

## Australia and Canada

- Australia: the Information Security Manual and the Essential Eight set the controls, and IRAP assesses a cloud
  service. The Digital Service Standard judges a public service.
- Canada: ITSG-33 sets the control catalogue, and a cloud service is assessed for its data's level, such as Protected B.

## United States, beyond the pack

- A sign-in for the public picks its assurance level from NIST SP 800-63-4, which `aidd-team:secure-coding` holds.
- A US privacy programme that needs a control mapping uses the NIST Privacy Framework 1.0. Version 1.1 is a draft.
- OMB memo M-26-05 (2026) leaves the secure-software attestation form to each agency's choice: check at source.
- CNSA 2.0 sets quantum-resistant algorithms for national security systems, with dated milestones: check at source.
- A state government's cloud buyer may ask for its own authorization program. The Spec names it.
