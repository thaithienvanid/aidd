# Worked examples: threat models

Load this when a threat entry or an abuse case reads as generic. Each pair shows a weak entry, a strong one, and the line that tells them apart. The names in angle brackets stand for the change's own parts; the examples teach the shape, never a domain.

## A threat tied to its boundary

- **Weak:** "Spoofing: an attacker could impersonate a user. Mitigation: use authentication."
- **Strong:** "`T-<COMPONENT>-03`, Spoofing at `<boundary between the caller and the service>`: a caller replays `<a token>` after the person signs out, because `<service>` checks only its signature. Mitigation: check `<revocation state>` on each request (owner: `<role>`). Abuse case: a token used after sign-out returns 401."
- **The difference:** the strong entry names the boundary, the asset, the exact weakness, the owner, and a test. "Use authentication" names a category, not a control.

## An abuse case the verifier can write

- **Weak:** "Test that authorization works."
- **Strong:** "As `<a user without the role>`, call `<operation>` on `<a resource another tenant owns>`. Expect 403, and `<the resource>` unchanged. It fails today without `<the check>`."
- **The difference:** a test names the actor, the action, the object, and the expected result, and it fails without the mitigation. A wish to "test it" is not a test.

## A delta, not a second model

- **Weak:** the Spec repeats the component's whole threat list, with two new rows somewhere inside it.
- **Strong:** the Spec lists only `T-<COMPONENT>-07` (added) and `T-<COMPONENT>-02` (changed: the new `<flow>` crosses its boundary too), and the component's model gains the same rows in the same change.
- **The difference:** one living model per component, and each Spec freezes only what it adds, changes, or retires.

## A residual risk a person can decide

- **Weak:** "Some risk remains."
- **Strong:** "Residual: `<threat id>` stays Medium until `<dependency>` supports `<control>`. The impact is `<what an actor could still do>`, for `<who>`. Above the profile's appetite, so `<person>` decides: accept until `<date>`, or wait."
- **The difference:** a person can only decide a risk that names its threat, its impact, its limit in time, and who decides.

## Needs validation, not a guess

- **Weak:** "The service might be exposed to the internet."
- **Strong:** "Needs validation: whether `<proxy or gateway>` allows `<path>` from outside. The repository can't show it. `<owner>` checks it with `<a command or a console view>`. Until then, `<threat id>` is treated as reachable."
- **The difference:** a fact outside the repository gets a name, an owner, and a check, never a severity on a guess.
