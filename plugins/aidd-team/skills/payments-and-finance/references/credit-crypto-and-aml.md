# Credit, crypto-assets, and financial crime: the payments-and-finance detail

Load this when a Spec lends money, offers a crypto-asset service, onboards a customer, or pays someone out. The pack's
standards are the source, and each date below was read there on 2026-10-22. In Specify, re-read a row's source when it
is more than six months old, and propose a changed row to aidd's `schemas/packs.json` and this file together.

## Consumer credit

- **APR** is the annual percentage rate: the yearly cost of credit, fees included, that the law makes a lender disclose.
- In the EU, the Consumer Credit Directive (EU) 2023/2225 applies from 2026-11-20. It covers buy now, pay later and loans
  below EUR 200. The lender gives the SECCI form before the contract, and assesses creditworthiness. A person can ask
  for a human review of an automated assessment.
- In the US, Regulation Z sets the APR and the other disclosures. Regulation B makes a decline state its specific
  principal reasons, a model's reasons included.
- The Credit disclosure tests prove each disclosure against the loan's terms, and each decline's reasons.

## Crypto-assets

- MiCA applies in full from 2024-12-30. National grandfathering ended on 2026-07-01, so every EU crypto-asset service
  provider now needs a MiCA authorisation. The Spec names it.
- The Transfer of Funds Regulation (EU) 2023/1113 carries the travel rule to crypto-asset transfers. Each transfer
  carries its originator's and its beneficiary's data, and a transfer to a self-hosted address has its own checks.

## KYC, AML, and sanctions screening

- The EU AML Regulation (EU) 2024/1624 applies from 2027-07-10, with crypto-asset service providers among its obliged
  entities. In the US, the Bank Secrecy Act's customer identification rule (31 CFR 1020.220) sets the minimum KYC for a bank.
- KYC is by risk. The Spec names what onboarding collects, what raises a customer's risk, and who reviews a match.
- Every payer and payee is screened against the sanctions lists of each market before money moves, such as the EU's
  consolidated list and OFAC's SDN list. A possible match holds the payment until a person decides.
- A payout to a seller, a claim payee, or a refund is screened the same way, and `aidd-team:insurance` points here.

## Payment rules already in force

- PSD2 strong customer authentication has applied to EEA electronic payments since 2019-09-14, with the RTS's exemptions.
  PSD3 and the Payment Services Regulation were agreed in 2026 but were not in the Official Journal on 2026-10-22, so PSD2
  still applies. Plan for them, and apply them once they are in force.
- DORA has applied to EU financial entities since 2025-01-17. Its incident clocks are `aidd-team:incident-response`'s.
- PCI DSS v4.0.1's future-dated requirements have applied since 2025-03-31, payment-page scripts (6.4.3) and tamper
  detection (11.6.1) among them.
- Verification of Payee has applied in the euro area since 2025-10-09, and applies in the rest of the EU from 2027-07-09.
