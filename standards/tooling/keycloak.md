---
id: tooling/keycloak
type: opinionated
fills: [product-defaults:authentication]
default: true
implements: secure-coding:OAuth 2.0 and OpenID Connect (RFC 9700)
roles: [architect, security-engineer, developer, sre, reviewer]
when_changed: ["keycloak/**", "**/keycloak/**", "**/*realm*.json"]
why: "Keycloak is a self-hosted identity server, so several apps share one sign-in, and single sign-on and sign-in through a customer's own identity provider come built in. It is a CNCF incubating project under Apache-2.0."
maturity: established
tool:
  name: keycloak
  registry: github
  package: keycloak/keycloak
version_policy: current_stable
checked_version: "26.8.1"
checked: "2026-11-04"
checked_by: agent:claude-code/claude-opus-5-5
source: https://raw.githubusercontent.com/keycloak/keycloak/main/README.md
evidence: Open Source Identity and Access Management
alternatives: [the framework's own authentication, ZITADEL, Ory, authentik, Auth0, Amazon Cognito, Microsoft Entra External ID]
status: active
---

# Keycloak signs people in for every app

It answers the authentication choice of `aidd-team:product-defaults` where the web framework has no sign-in of its own. It also fits where several apps, or a customer's SSO, need one identity server. Keycloak is under the Apache-2.0 license. The CNCF accepted it as an incubating project on April 10, 2023.

## What the team does

- Run Keycloak as a service of its own, from its official container image pinned by digest, with its own database and a tested restore. Upgrade one release at a time, in staging first.
- Keep each realm's configuration in the repository as an export, and apply it from CI. A change to a client, a role, or a sign-in rule is then a change in the repository. It is never a click in the admin console alone.
- Register each app as its own client, with exact redirect URIs. The app signs in with a maintained OpenID Connect client library and checks each token as `aidd-team:secure-coding`'s `references/authentication.md` says.
- Set the factors and the password policy in the realm, once, rather than in each app.
- Connect a customer's SSO through Keycloak's identity brokering, so each app trusts one issuer for every tenant.
- Keep the admin console and the admin API off the public sign-in host.
