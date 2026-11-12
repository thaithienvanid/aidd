---
type: release
environment: "{{environment}}"
released_at: "{{released_at}}"
commit: "{{commit}}"
specs: []
rolled_back: []
---

# Release: {{environment}} ({{released_day}})

<!-- Recorded by `aidd new release <environment> --commit <sha>`.
     `released_at` is the instant users had this release, and aidd orders releases of one environment by it.
     Never edit or delete this file to roll back: write a new release file for the rollback commit and name each removed Spec in `rolled_back`. -->

Released to {{environment}} at commit `{{commit}}`.
