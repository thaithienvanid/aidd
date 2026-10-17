# Domain packs

Every domain has a pack: a skill named `aidd-team:<pack>`, generated from `schemas/roles.json`. Each pack follows one template, in this order:

**Contents**

<!-- aidd:gen toc -->
- (no sections)
<!-- aidd:end -->

1. Scope: applies when, not when, and the neighbours.
2. Standards: at most ten, labelled S1 to S10.
3. Dated obligations: regulated and platform packs only.
4. Checklist by loop step: one to four rows a step, each citing its standard, and the product defaults as one row.
5. Test commands.
6. Owned elsewhere.
7. References.
8. Keep it current.

- Load the packs for every domain the change touches, on top of your role's playbook, for the steps you work in. Name each in the Spec's Context. A pack does not count against a Task's `skills`.
- A pack's test commands are best practices the gate runs, not prose. Put them in the Spec's `tests.commands`, so a red one blocks the merge. A line "From `aidd-team:<owner>`" names a test another skill owns; take it from there, once. A test command that needs a third-party account or a paid service is optional: use it only where the project already has it.
- A pack a role preloads loads into every run of that role, so it lists each standard's name and edition only. The checked date, the source, and when each is due are in [roles.md](roles.md), Preloaded skills.
- A fact lives with one owner (the product defaults, the shared scanners, the AI evals, the breach clocks), and the others point to it.
- No pack for the domain, or a standard `aidd eval standards` lists as due? The loop contract's research-first rule applies. Look up the authoritative source, record the edition in the Spec, and propose the pack or the update. `aidd eval packs` fails on a pack or practice skill that breaks its template.

<!-- aidd:gen roles:domains -->
| Domain | Pack | When the change touches | Standard | Edition | Checked |
| --- | --- | --- | --- | --- | --- |
| Web front end | `aidd-team:web-front-end` | HTML, CSS, browser code | WCAG 2.2, level AA | 2.2 | checked 2026-10-16 |
|  |  |  | Core Web Vitals (LCP, INP, CLS) | 2024 thresholds | checked 2026-10-16 |
|  |  |  | Content Security Policy, with Trusted Types for DOM injection sinks | Level 2; Trusted Types (W3C Working Draft, 2026-06-23) | checked 2026-10-16 |
|  |  |  | OWASP Cheat Sheet Series (XSS, CSRF, clickjacking) | — | reviewed 2026-10-16 |
|  |  |  | Design tokens (W3C Design Tokens format) and a design system over one-off styles | 2025.10 | checked 2026-10-16 |
|  |  |  | Baseline (web-features): the browser support target | Baseline Widely available | checked 2026-10-16 |
|  |  |  | Subresource Integrity and Permissions Policy | SRI (W3C Recommendation, 2016); Permissions Policy (W3C Working Draft, 2026-09-22) | checked 2026-10-16 |
|  |  |  | ePrivacy Directive Art. 5(3): consent before storing or reading on a user's device | Directive 2002/58/EC, Art. 5(3); EDPB Guidelines 2/2023 v2.0 | checked 2026-10-16 |
|  |  |  | Rendering on the web: static, server, and client rendering, and hydration | web.dev | checked 2026-10-17 |
| APIs and services | `aidd-team:apis-and-services` | HTTP, gRPC, events, webhooks | OpenAPI Specification | 3.2.1 | checked 2026-10-16 |
|  |  |  | RFC 9457 problem details | 2023 | checked 2026-10-16 |
|  |  |  | OWASP API Security Top 10 | 2023 | checked 2026-10-16 |
|  |  |  | Idempotency keys and rate limits | draft-ietf-httpapi-idempotency-key-header-07; draft-ietf-httpapi-ratelimit-headers-11 | checked 2026-10-16 |
|  |  |  | Semantic Versioning | 2.0.0 | checked 2026-10-16 |
|  |  |  | GraphQL specification | September 2025 | checked 2026-10-16 |
|  |  |  | HTTP Deprecation and Sunset header fields | RFC 9745; RFC 8594 | checked 2026-10-16 |
|  |  |  | Standard Webhooks: signed, identified, and timestamped webhook delivery | — | checked 2026-10-16 |
|  |  |  | RFC 6455 The WebSocket Protocol | RFC 6455 | checked 2026-10-17 |
|  |  |  | Server-sent events (EventSource) | WHATWG HTML Living Standard | checked 2026-10-17 |
| Mobile apps | `aidd-team:mobile-apps` | iOS, Android, cross-platform | OWASP MASVS, MASTG, and MASWE | MASVS 2.1, MASTG v2, MASWE v1.0.0 | checked 2026-10-16 |
|  |  |  | Apple App Review Guidelines and Human Interface Guidelines | App Review Guidelines of 2026-06-08 | checked 2026-10-16 |
|  |  |  | Apple App Privacy details, privacy manifests, and App Tracking Transparency | — | checked 2026-10-16 |
|  |  |  | App Store Connect upload requirements | — | checked 2026-10-16 |
|  |  |  | Google Play Developer Program Policy | — | checked 2026-10-16 |
|  |  |  | Google Play Data safety, with its data deletion answers | — | checked 2026-10-16 |
|  |  |  | Google Play target API level and new-account testing | Android 16 (API level 36) | checked 2026-10-16 |
|  |  |  | Android developer verification | — | checked 2026-10-16 |
|  |  |  | Android vitals bad behavior thresholds, with Apple's launch-time and hang metrics (MetricKit, Xcode Organizer) | Google Play's thresholds: user-perceived crash rate 1.09% and ANR rate 0.47% overall, 8% per phone model | checked 2026-10-17 |
| Desktop apps | `aidd-team:desktop-apps` | macOS and Windows apps, Electron, Tauri, their signing, updater, and stores | Apple notarization: Developer ID signing, the hardened runtime, and a stapled ticket | — | checked 2026-10-16 |
|  |  |  | Authenticode code signing with a certificate from the Microsoft Trusted Root Program, verified with SignTool | — | checked 2026-10-16 |
|  |  |  | Microsoft Store Policies | 7.20 | checked 2026-10-16 |
|  |  |  | Apple App Review Guidelines and Human Interface Guidelines | App Review Guidelines of 2026-06-08 | checked 2026-10-16 |
|  |  |  | Electron security checklist and fuses | — | checked 2026-10-16 |
|  |  |  | Tauri 2 security model: capabilities, CSP, the isolation pattern, and the signed updater | Tauri 2 | checked 2026-10-16 |
| AI features | `aidd-team:ai-features` | a model call, retrieval, embeddings, or fine-tuning | NIST AI RMF and NIST AI 600-1 | AI RMF 1.0; NIST AI 600-1 | checked 2026-10-16 |
|  |  |  | OWASP Top 10 for LLM Applications | 2026 edition | checked 2026-10-16 |
|  |  |  | EU AI Act | Regulation (EU) 2024/1689 as amended by Regulation (EU) 2026/1744 (Digital Omnibus on AI) | checked 2026-10-16 |
|  |  |  | Evals with golden datasets, and model cards | — | reviewed 2026-10-16 |
|  |  |  | Human-AI interaction guidelines: Microsoft's 18 Guidelines and the Google PAIR Guidebook | Guidelines for Human-AI Interaction (CHI 2019) | checked 2026-10-16 |
|  |  |  | Output guardrails and input filters as a named layer, mapped to OWASP LLM01:2026 and LLM10:2026 | — | reviewed 2026-10-16 |
|  |  |  | Token and GPU cost as a budgeted, allocated unit metric, reported like any other FinOps scope | — | checked 2026-10-16 |
|  |  |  | Model and system cards for AI features, datasheets for datasets, and the Article 50 marking and disclosure text users see | — | reviewed 2026-10-16 |
| AI agents and tools | `aidd-team:ai-agents-and-tools` | an agent, tool calling, MCP, or A2A | OWASP Top 10 for Agentic Applications | 2026 | checked 2026-10-16 |
|  |  |  | MITRE ATLAS | ATLAS data v2026.09 | checked 2026-10-16 |
|  |  |  | MCP and A2A, with the MCP security best practices | 2026-07-28 revision | checked 2026-10-16 |
|  |  |  | Least privilege per tool and human approval for irreversible actions | — | checked 2026-10-16 |
|  |  |  | OpenTelemetry GenAI semantic conventions | — | checked 2026-10-16 |
|  |  |  | Agent architecture patterns: routing, orchestrator-workers, evaluator-optimizer, and a plain workflow where an agent is not needed; context engineering for the window | — | checked 2026-10-16 |
|  |  |  | MAESTRO 7-layer threat modeling for agentic AI, alongside STRIDE for classic data flows | — | reviewed 2026-10-16 |
|  |  |  | OWASP Agent Control Standard and the GenAI Security Industry Framework Crosswalk, which maps 51 entries across 26 frameworks | OWASP Agent Control Standard (ACS) | checked 2026-10-16 |
| Data and analytics | `aidd-team:data-and-analytics` | pipelines, warehouses, schemas, ML data | ISO/IEC 25012 data quality model | ISO/IEC 25012:2008 | checked 2026-10-16 |
|  |  |  | Open Data Contract Standard (ODCS) | v3.2.0 | checked 2026-10-16 |
|  |  |  | Open Data Product Standard (ODPS) | v1.1.0 | checked 2026-10-16 |
|  |  |  | OpenLineage | 1.53.0 | checked 2026-10-16 |
|  |  |  | Analytics engineering in dbt: tests on every model, model contracts on published models, and the semantic layer as the one definition of a metric | — | reviewed 2026-10-16 |
|  |  |  | Streaming semantics stated against the transport's own guarantee: idempotent producers and transactions where Kafka carries the data | — | checked 2026-10-16 |
|  |  |  | PostgreSQL full text search | PostgreSQL 18 | checked 2026-10-17 |
| Cloud and infrastructure | `aidd-team:cloud-and-infrastructure` | IaC, containers, Kubernetes, functions, CI/CD, or cloud cost | AWS Well-Architected Framework | 2024-11-06 update | checked 2026-10-16 |
|  |  |  | Google Cloud Well-Architected Framework | 2026-01-28 review | checked 2026-10-16 |
|  |  |  | Cloudflare Reference Architectures | 2026-06-05 update | checked 2026-10-16 |
|  |  |  | FinOps Framework: budgets, allocation by tags, and unit cost | FinOps Framework 2026 | checked 2026-10-16 |
|  |  |  | CIS Benchmarks | — | reviewed 2026-10-16 |
|  |  |  | Kubernetes Pod Security Standards: workloads at the `restricted` Pod Security profile | — | reviewed 2026-10-16 |
|  |  |  | CIS Kubernetes Benchmark | 2.0.1 | checked 2026-10-16 |
|  |  |  | Policy as code (Open Policy Agent, Kyverno) | — | checked 2026-10-16 |
|  |  |  | AWS Well-Architected Sustainability Pillar | 2024-11-06 | checked 2026-10-17 |
|  |  |  | Software Carbon Intensity (SCI) | SCI 1.1.0 | checked 2026-10-17 |
| Payments and finance | `aidd-team:payments-and-finance` | card data, ledgers, money movement | PCI DSS | v4.0.1 | checked 2026-10-16 |
|  |  |  | PSD2 strong customer authentication and its RTS | Directive (EU) 2015/2366; Delegated Regulation (EU) 2018/389 | checked 2026-10-16 |
|  |  |  | PSD3 and the Payment Services Regulation (PSR) | Final compromise texts, 2026 (interinstitutional files 2023/0210 and 2023/0209) | checked 2026-10-16 |
|  |  |  | EMV 3-D Secure | Protocol and Core Functions Specification v2.3.1.1 | checked 2026-10-16 |
|  |  |  | EMV payment tokenisation (network tokens) | Technical Framework v2.4 | checked 2026-10-16 |
|  |  |  | EU Digital Operational Resilience Act | Regulation (EU) 2022/2554 | checked 2026-10-16 |
|  |  |  | Double-entry and idempotent money movement | — | reviewed 2026-10-16 |
|  |  |  | EU Consumer Credit Directive (CCD2) | Directive (EU) 2023/2225 | checked 2026-10-17 |
|  |  |  | US consumer credit: Truth in Lending (Regulation Z) and Equal Credit Opportunity (Regulation B) | 12 CFR Part 1026; 12 CFR Part 1002 | checked 2026-10-17 |
|  |  |  | MiCA: Markets in Crypto-Assets | Regulation (EU) 2023/1114 | checked 2026-10-17 |
| Commerce and marketplaces | `aidd-team:commerce-and-marketplaces` | orders, stock, sellers, or reviews | EU Digital Services Act: online marketplaces (trader traceability, compliance by design, random checks) | Regulation (EU) 2022/2065, Articles 30 to 32 | checked 2026-10-17 |
|  |  |  | EU General Product Safety Regulation | Regulation (EU) 2023/988 | checked 2026-10-17 |
|  |  |  | INFORM Consumers Act: verifying and disclosing high-volume third-party sellers | 15 U.S.C. 45f | checked 2026-10-17 |
|  |  |  | FTC Trade Regulation Rule on the Use of Consumer Reviews and Testimonials | 16 CFR Part 465 | checked 2026-10-17 |
|  |  |  | Accessibility law for the product, not only its docs: the European Accessibility Act, Section 508, and the ADA where they reach | Directive (EU) 2019/882 | checked 2026-10-16 |
|  |  |  | Order and stock integrity: one order state machine, stock held with an expiry, and idempotent fulfillment and refunds | — | reviewed 2026-10-17 |
| Health | `aidd-team:health` | clinical or patient data, medical devices | HIPAA Privacy and Security Rules | 45 CFR Parts 160 and 164 | checked 2026-10-16 |
|  |  |  | HL7 FHIR | R4 4.0.1 | checked 2026-10-16 |
|  |  |  | HL7 US Core and SMART App Launch | US Core 9.0.0 (STU 9); SMART App Launch 2.2.0 | checked 2026-10-16 |
|  |  |  | ONC HTI rules and information blocking (45 CFR Parts 170 and 171) | HTI-1 to HTI-4 final rules | checked 2026-10-16 |
|  |  |  | FD&C Act section 524B for cyber devices, with FDA's premarket cybersecurity guidance | Section 524B; premarket cybersecurity guidance, February 2026 | checked 2026-10-16 |
|  |  |  | IEC 81001-5-1 security activities in the health software life cycle | IEC 81001-5-1:2021 | checked 2026-10-16 |
|  |  |  | IEC 62304 for medical device software | 2006 + A1:2015 | checked 2026-10-16 |
|  |  |  | ISO 14971 risk management | 2019 | checked 2026-10-16 |
| Embedded, automotive, and industrial | `aidd-team:embedded-automotive-industrial` | firmware, vehicles, connected devices, OT | MISRA C or MISRA C++ | MISRA C:2025; MISRA C++:2023 | checked 2026-10-16 |
|  |  |  | ISO 26262 and ISO/SAE 21434 | 26262:2018, 21434:2021 | checked 2026-10-16 |
|  |  |  | IEC 61508 | 2010 | checked 2026-10-16 |
|  |  |  | IEC 62443 | series, with 62443-4-1:2018 and 62443-4-2:2019 | checked 2026-10-16 |
|  |  |  | UN Regulations No. 155 (cyber security management system) and No. 156 (software update management system), with ISO 24089 for software update engineering | UN R155 and UN R156; ISO 24089:2023 with Amd 1:2024 | checked 2026-10-16 |
|  |  |  | ISO 21448 safety of the intended functionality (SOTIF) | ISO 21448:2022 | checked 2026-10-16 |
|  |  |  | EU Cyber Resilience Act for products with digital elements | Regulation (EU) 2024/2847 | checked 2026-10-16 |
|  |  |  | Radio equipment cybersecurity (RED Delegated Regulation (EU) 2022/30, EN 18031) and ETSI EN 303 645 for consumer IoT | EN 18031-1, -2, and -3:2024; ETSI EN 303 645 V3.1.3 | checked 2026-10-16 |
| Public sector and regulated security | `aidd-team:public-sector` | government or audited systems | NIST CSF | 2.0 | checked 2026-10-16 |
|  |  |  | NIST SP 800-53 | Rev. 5, Release 5.2.0 | checked 2026-10-16 |
|  |  |  | FedRAMP Rev. 5 baselines, where they apply | Rev. 5 | checked 2026-10-16 |
|  |  |  | FedRAMP 20x | Consolidated Rules for 2026 | checked 2026-10-16 |
|  |  |  | FIPS 140-3 cryptography | FIPS 140-3 | checked 2026-10-16 |
|  |  |  | NIST post-quantum standards (FIPS 203, 204, 205) for new cryptography | FIPS 203, FIPS 204, FIPS 205 | checked 2026-10-16 |
|  |  |  | NIST Privacy Framework where a US privacy-programme mapping is needed | Version 1.0 | checked 2026-10-16 |
|  |  |  | CycloneDX cryptography bill of materials (CBOM) | 1.7.2 | checked 2026-10-16 |
| Products for children | `aidd-team:products-for-children` | users under 13, or under 16 in the EU | COPPA | 16 CFR Part 312, as amended 2025-04-22 | checked 2026-10-16 |
|  |  |  | UK Age Appropriate Design Code | 2021 | checked 2026-10-16 |
|  |  |  | GDPR | Regulation (EU) 2016/679 | checked 2026-10-16 |
|  |  |  | UK Online Safety Act 2023: the children's safety duties and Ofcom's Protection of Children Codes | Online Safety Act 2023; Protection of Children Codes (2025) | checked 2026-10-16 |
|  |  |  | EU Digital Services Act Article 28 and the Commission's guidelines on the protection of minors | Regulation (EU) 2022/2065, Art. 28; guidelines of 2025-07-14 | checked 2026-10-16 |
|  |  |  | ISO/IEC 27566-1 age assurance systems framework | ISO/IEC 27566-1:2025 | checked 2026-10-16 |
| Education | `aidd-team:education` | student records, courses, grades, or learning tools | FERPA | 34 CFR Part 99 | checked 2026-10-17 |
|  |  |  | 1EdTech Learning Tools Interoperability, with LTI Advantage | LTI 1.3 | checked 2026-10-17 |
|  |  |  | 1EdTech OneRoster | OneRoster 1.2 | checked 2026-10-17 |
|  |  |  | ADA Title II web and mobile app accessibility rule (WCAG 2.1 AA for state and local governments, public schools and universities among them) | 28 CFR Part 35, Subpart H, compliance dates as extended on 2026-04-20 | checked 2026-10-17 |
|  |  |  | WCAG 2.2, level AA | 2.2 | checked 2026-10-16 |
|  |  |  | EU AI Act | Regulation (EU) 2024/1689 as amended by Regulation (EU) 2026/1744 (Digital Omnibus on AI) | checked 2026-10-16 |
|  |  |  | Academic records: a grade or credit change is an attributable, reasoned event kept in history, never an overwrite | — | reviewed 2026-10-17 |
| HR and workforce | `aidd-team:hr-and-workforce` | candidates, employees, pay, or hiring decisions | EU AI Act | Regulation (EU) 2024/1689 as amended by Regulation (EU) 2026/1744 (Digital Omnibus on AI) | checked 2026-10-16 |
|  |  |  | NYC Local Law 144: automated employment decision tools (bias audit and notice) | Local Law 144 of 2021, with the DCWP rule | checked 2026-10-17 |
|  |  |  | Uniform Guidelines on Employee Selection Procedures (adverse impact and the four-fifths rule) | 29 CFR Part 1607 | checked 2026-10-17 |
|  |  |  | Evaluation beyond accuracy: calibration, robustness, and bias and fairness testing against a stated bias taxonomy, with the results in the model card | NIST SP 1270 | checked 2026-10-16 |
|  |  |  | EU Pay Transparency Directive | Directive (EU) 2023/970 | checked 2026-10-17 |
|  |  |  | FLSA recordkeeping | 29 CFR Part 516 | checked 2026-10-17 |
|  |  |  | GDPR | Regulation (EU) 2016/679 | checked 2026-10-16 |
|  |  |  | Effective-dated workforce records: every change to pay, role, or manager carries its effective date and its approver, never an overwrite | — | reviewed 2026-10-17 |
| Privacy by default | `aidd-team:privacy-by-default` | personal data: user, customer, account, member, patient, or contact records, consent, data-subject requests, or a `gdpr` target in `project.compliance.targets` | GDPR by article: Art. 5 principles, Art. 6 lawful basis, Art. 7 consent, Art. 12-22 data-subject rights, Art. 25 by design and by default, Art. 28 processors, Art. 30 records of processing, Art. 32 security, Art. 33-34 breach, Art. 35 DPIA, Art. 44-49 transfers | Regulation (EU) 2016/679 | checked 2026-10-16 |
|  |  |  | CCPA/CPRA as the comparable US regime: notice at collection, and the rights to know, delete, correct, and opt out of sale or sharing | CCPA regulations effective 2026-01-01 | checked 2026-10-16 |
|  |  |  | Data subject request fulfillment built into the pipeline (export and erase by subject key), under GDPR and CCPA/CPRA as amended | Regulation (EU) 2016/679 | checked 2026-10-16 |
|  |  |  | DPIA method and template: the EDPB DPIA Template, which national authorities will adopt as their unique or meta-template | EDPB DPIA Template (consultation draft) | checked 2026-10-16 |
|  |  |  | Cross-border transfers: the mechanism, a transfer impact assessment, and the current adequacy map | Implementing Decision (EU) 2021/914 | checked 2026-10-16 |
|  |  |  | Automated PII discovery and classification in tables, columns, and free text, with the classification driving retention, masking, and access rules | — | reviewed 2026-10-16 |
|  |  |  | LINDDUN over the data-flow diagram the threat model draws, for the risks to people | — | reviewed 2026-10-16 |
| Internationalization | `aidd-team:internationalization` | more than one language or region | Unicode CLDR | CLDR 48 | checked 2026-10-16 |
|  |  |  | BCP 47 language tags | RFC 5646, 2009 | checked 2026-10-16 |
|  |  |  | ICU MessageFormat, with MessageFormat 2 where the runtime has it | MessageFormat 2.0 (LDML 48) | checked 2026-10-16 |
|  |  |  | W3C internationalization best practices | — | reviewed 2026-10-16 |
|  |  |  | Translated documentation: XLIFF for exchange, gettext for source strings, and a translation memory that keeps glossary terms stable | XLIFF Core 2.1 | checked 2026-10-16 |
|  |  |  | IANA Time Zone Database (tzdata) | 2026e | checked 2026-10-16 |
|  |  |  | Unicode Bidirectional Algorithm (UAX #9) | Revision 52 (Unicode 18.0.0) | checked 2026-10-16 |
| Multi-tenant SaaS | `aidd-team:multi-tenant-saas` | code that reads or writes data belonging to a tenant, organization, workspace, or customer account in a shared deployment | OWASP API1:2023 Broken Object Level Authorization, applied across tenants | 2023 | checked 2026-10-16 |
|  |  |  | AWS Well-Architected SaaS Lens: tenant isolation, noisy neighbours, and tenant cost | 2023-04-04 | checked 2026-10-16 |
|  |  |  | PostgreSQL row security policies as a second layer of tenant isolation | PostgreSQL 18, section 5.9 | checked 2026-10-16 |
| Enterprise controls | `aidd-team:enterprise-controls` | a product whose `.aidd/config.yaml` sets `project.compliance` targets or uses the audited profile. Or code that implements sign-in, SSO, SCIM, MFA, sessions, audit logs, an admin console, or another control an enterprise buyer or an auditor asks about | SOC 2 Trust Services Criteria (CC6 logical access, CC7 system operations, CC8 change management, A1 availability, C1 confidentiality) | 2017, with the 2022 revised points of focus | checked 2026-10-16 |
|  |  |  | ISO/IEC 27001:2022 Annex A, the technological controls (8.x) and the incident controls (5.24 to 5.28) | ISO/IEC 27001:2022 with Amd 1:2024 | checked 2026-10-16 |
|  |  |  | GDPR Art. 25 (data protection by design and by default), Art. 32 (security of processing), and Art. 33 and 34 (breach notification) | Regulation (EU) 2016/679 | checked 2026-10-16 |
|  |  |  | OWASP ASVS 5.0: Level 1 by default, Level 2 for authentication, session, and admin surfaces when compliance is on | 5.0.0 | checked 2026-10-16 |
|  |  |  | NIST SSDF (SP 800-218) | SP 800-218 v1.1 | checked 2026-10-16 |
|  |  |  | Least-privilege CI: OIDC federation over long-lived secrets, actions pinned by commit SHA | — | checked 2026-10-16 |
|  |  |  | SBOM in CycloneDX (with ML-BOM) or SPDX, and VEX | 1.7.2 | checked 2026-10-16 |
| Package publishing | `aidd-team:package-publishing` | a package or formula published to a public registry | Trusted publishing: OIDC from CI to the package registry, no long-lived token | OpenSSF Securing Software Repositories WG, May 2025 | checked 2026-10-16 |
|  |  |  | SLSA | v1.2, 2025 | checked 2026-10-16 |
|  |  |  | Semantic Versioning | 2.0.0 | checked 2026-10-16 |
|  |  |  | Maven Central publishing requirements | — | checked 2026-10-16 |
|  |  |  | Homebrew Acceptable Formulae (homebrew/core) | — | checked 2026-10-16 |
|  |  |  | OpenSSF Open Source Project Security Baseline | v2026.08.28 | checked 2026-10-16 |
|  |  |  | OpenSSF Scorecard | v5.5.0 | checked 2026-10-16 |
|  |  |  | EU Cyber Resilience Act: open-source software stewards (Art. 24) | Regulation (EU) 2024/2847 | checked 2026-10-16 |
| Extensions and marketplace apps | `aidd-team:extensions-and-marketplace-apps` | a browser or editor extension, or an app a host's marketplace lists | Chrome Web Store program policies, with the Manifest V3 requirements | — | checked 2026-10-16 |
|  |  |  | Firefox add-on policies (AMO) | — | checked 2026-10-16 |
|  |  |  | Publishing VS Code extensions to the Visual Studio Marketplace | — | checked 2026-10-16 |
|  |  |  | Shopify App Store requirements | — | checked 2026-10-16 |
|  |  |  | Slack Marketplace app guidelines and requirements | — | checked 2026-10-16 |
|  |  |  | Atlassian Marketplace security requirements for cloud apps | — | checked 2026-10-16 |
|  |  |  | Microsoft Teams Store validation guidelines | — | checked 2026-10-16 |
|  |  |  | Salesforce AgentExchange (formerly AppExchange) security review | — | checked 2026-10-16 |
<!-- aidd:end -->
