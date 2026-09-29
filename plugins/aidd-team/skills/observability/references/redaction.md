# Redaction

Load this when you add logging, tracing, or error reporting that may carry user data or credentials, or when you build the redaction step itself.

## Log the fact, not the value

| Instead of | Log |
| --- | --- |
| `reset link sent to ana@example.com` | `reset link sent` with `user_id` |
| `token abc123 rejected` | `token rejected` with the token's id or a short hash prefix, and the reason |
| the full request body on error | the route, the status, the field names that failed validation |
| `card 4111... declined` | `card declined` with the payment id and the decline code |

## The mechanism

One function, called by the logger's processor (or formatter) and by the tracing exporter's attribute hook, so no call site can forget it.

- A deny-list of keys, compared case-insensitively and by substring, so `accessToken`, `X-Auth-Token`, and `refresh_token` all match `token`: `password`, `passwd`, `secret`, `token`, `authorization`, `cookie`, `session`, `api_key`, `apikey`, `private_key`, `email`, `phone`, `ssn`, plus the project's own personal-data fields.
- Walks nested maps and lists to any depth, and structured values inside strings where the project logs JSON strings.
- Replaces the value with a fixed marker (`[REDACTED]`), never a partial value that can be joined back.
- Prefers false positives: masking a harmless field is a small cost; leaking one token is an incident.
- Also runs on exception messages and error-report payloads, which often carry the request.

## The unit test

```text
given   {"user": {"Email": "ana@example.com", "id": 7},
         "headers": [{"name": "X-Auth-Token", "value": "..."}],
         "session": {"accessToken": "abc", "refresh_TOKEN": "def"},
         "note": "kept"}
when    passed through the redaction function
then    Email, accessToken, refresh_TOKEN are "[REDACTED]"
and     the header entry whose name matches the deny-list has its value masked
and     user.id and note are unchanged
and     the input object is not mutated
```

Add a second test through the real logger: emit a line with that payload, capture the output, and assert neither `ana@example.com` nor `abc` appears anywhere in it.

## Security events worth a name

Log each with a stable event name, the actor, the source address, and the outcome; the OWASP Application Logging Vocabulary gives names such as `authn_login_success`, `authn_login_fail`, and `authz_fail`.

- Authentication success and failure, and repeated failures from one source or for one account.
- Authorization denial, with the resource and the action attempted.
- Privileged or administrative operations (role changes, exports, configuration changes), with the actor.
- Rate-limit hits and input rejected as malicious.
