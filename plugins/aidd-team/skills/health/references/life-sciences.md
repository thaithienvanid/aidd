# Life sciences: GxP software and study data

Load this when a change touches software that a good manufacturing, clinical, or laboratory practice rule (GxP) covers: manufacturing and quality systems, a clinical trial system, a laboratory system, or study data for a submission. Each source was read on 2026-10-22.

## Before the first edit

GxP software is in the scope of 21 CFR Part 11 (US) and EU GMP Annex 11. Name the records and signatures the change touches, and the intended use and its risk (CSA). One thing is always true: a GxP record changes only with an audit trail, and a signature stays bound to what was signed. The case a plan misses is a bulk correction script, or a signed record edited after signing.

## Part 11 and Annex 11, as controls a Spec names

| Control | What the product does | Source |
| --- | --- | --- |
| Validation | The system is shown fit for its intended use, with the effort the risk calls for (CSA, GAMP 5) | 21 CFR 11.10(a); Annex 11, 4 |
| Audit trail | Secure, computer-generated, and time-stamped: it records who created, changed, or deleted a record, and when. A change never hides the earlier value, and the trail is kept as long as the record | 21 CFR 11.10(e); Annex 11, 9 |
| Access | Only authorized people use the system, sign, or change a record, checked by the system | 21 CFR 11.10(d), (g); Annex 11, 12 |
| Signature | It shows the signer's printed name, the date and time, and its meaning (review, approval, authorship). It's linked to its record so it can't be copied or moved to another | 21 CFR 11.50, 11.70 |
| Copies | Accurate, complete copies in human-readable and electronic form, for an inspection | 21 CFR 11.10(b); Annex 11, 8 |
| Periodic review | The system is reviewed on a schedule to show it stays validated | Annex 11, 11 |

Sources: [21 CFR Part 11](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-11) and [EudraLex Volume 4](https://health.ec.europa.eu/medicinal-products/eudralex/eudralex-volume-4_en), where Annex 11 is still the January 2011 revision.

| Test | Proves | How |
| --- | --- | --- |
| GxP audit trail test | every create, change, and delete of a GxP record logs who, when, the old and new value, and why, and a signed record that changes loses its signature | integration tests over every write path: the application, admin tools, imports, and data-fix scripts, in the Spec's `tests` |

## Computer Software Assurance

FDA's CSA guidance (February 2026, which superseded the September 2025 final guidance) applies to production and quality management system software. Assurance follows the risk of the intended use. A function whose failure could harm product quality or patient safety gets scripted tests with recorded results. A lower-risk function gets unscripted or exploratory testing, recorded briefly. A vendor's own testing counts where it's documented. In aidd terms, the risk sits in the Spec's Context, and the test commands and their recorded runs are the evidence.

Source: [FDA, Computer Software Assurance for Production and Quality Management System Software](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/computer-software-assurance-production-and-quality-management-system-software).

## GAMP 5

ISPE's GAMP 5 Second Edition (July 2022) is the industry's guide to a risk-based life cycle for GxP computerized systems. It covers supplier assessment, agile development, service providers, and software tools. Use its terms in the Spec when a quality unit expects them. Source: [ISPE](https://ispe.org/publications/guidance-documents/gamp-5-guide-2nd-edition).

## Study data: CDISC

FDA requires standardized study data in the formats its Data Standards Catalog names, under FD&C Act section 745A(a). For CDISC, these are SDTM for tabulations, ADaM for analysis data, SEND for nonclinical data, Define-XML, and the controlled terminology. CDASH, for collecting the data, is recommended, not required. A change that exports study data names the versions the catalog lists for its submission date. Its test validates each dataset against them with a conformance rules engine, such as CDISC CORE. Sources: [CDISC standards](https://www.cdisc.org/standards) and [FDA, standardized study data](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/providing-regulatory-submissions-electronic-format-standardized-study-data).

## Drafts to design for, not claim (emerging)

The European Commission consulted on a revised Annex 11, a revised Chapter 4 on documentation, and a new Annex 22 on artificial intelligence, from 2025-07-07 to 2025-10-07. None was final on 2026-10-22. The Annex 22 draft covers AI models in critical GxP applications. Until it's final, an AI feature in a GxP process records its intended use, its test data, and its human review, which `aidd-team:ai-features` asks for anyway. Source: [the consultation](https://health.ec.europa.eu/consultations/stakeholders-consultation-eudralex-volume-4-good-manufacturing-practice-guidelines-chapter-4-annex_en).
