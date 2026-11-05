# Authentication and sessions

Load this when a change signs a person or a client in, issues or checks a token, or keeps a session. Also load it when a change adds a factor or a recovery path. ASVS 5.0.0 chapters V6 Authentication, V7 Session Management, V9 Self-contained Tokens, and V10 OAuth and OIDC are the requirements. NIST SP 800-63B-4 sets the authenticator rules. What an enterprise buyer asks for (SSO, SCIM, an admin's MFA setting) is `aidd-team:enterprise-controls`, `references/readiness.md`.

## OAuth 2.0 and OpenID Connect (RFC 9700)

- Authorization code with PKCE for every client, public or confidential. Never the implicit grant or the resource owner password grant.
- Redirect URIs compared by exact string match; `state` (or the OIDC `nonce`) bound to the user agent; no open redirector on the client or the server.
- Access tokens short-lived, and restricted to their audience and the least scope. Sender-constrained (DPoP or mutual TLS) where the risk warrants it.
- Refresh tokens rotated on use or sender-constrained, and revoked at sign-out.
- Validate an ID token or a JWT fully: signature with an allowed algorithm (never `none`), `iss`, `aud`, `exp`, and `nbf`. Never trust a token's own key or algorithm header.
- Use the provider's certified library, never a hand-rolled flow.

## Passwords, passkeys, and factors (SP 800-63B-4)

- Offer passkeys (WebAuthn) as the phishing-resistant factor, bound to the relying party ID. A synced passkey is fine up to AAL2, and AAL3 needs a device-bound one.
- Passwords:
  - at least 15 characters where a password is the only factor (8 with a second factor), and at least 64 allowed;
  - every printable character and space accepted;
  - checked against a blocklist of breached and common passwords;
  - no composition rules and no scheduled rotation;
  - hashed with Argon2id, scrypt, or bcrypt at current cost.
- Throttle failed attempts per account and per source. SP 800-63B-4 allows at most 100 consecutive failures on one authenticator before disabling it. State the threshold, and give an unlock path that does not depend on support.
- SMS and voice codes are a restricted authenticator. Offer a stronger factor alongside, and never make them an admin's only second factor.
- Recovery is as strong as sign-in: a recovery code or a second bound authenticator, never an email link alone for a privileged account. Every recovery notifies the account's contacts and revokes other sessions.

## Sessions

- Rotate the session identifier at sign-in, at a step-up, and at a privilege change. Invalidate it server side at sign-out, and after an idle and an absolute timeout.
- Cookies `Secure`, `HttpOnly`, and `SameSite=Lax` or `Strict`, with the `__Host-` prefix where the path allows. No session identifier in a URL or a log.
- Re-authenticate before a sensitive action (changing the email, a factor, or a payout).
- A password change or a factor removal ends every other session.

## Tests

| Test | Proves |
| --- | --- |
| Session rotation test | the identifier before sign-in is not valid after it; sign-out and the timeouts end the session server side |
| Lockout and throttling tests | the stated threshold throttles per account and per source; the unlock path works; the error does not reveal whether the account exists |
| MFA and recovery tests | a missing or wrong factor is refused; recovery revokes other sessions and notifies; a refresh token reused after rotation is refused |
