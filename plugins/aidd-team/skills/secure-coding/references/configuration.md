# The configuration boundary

Load this when a change adds a setting, reads the environment, or touches secrets.

## One boundary

- One module (`config`, `settings`) reads environment variables, files, and the secret manager, and validates every value at start-up. It fails the start when a required value is missing or malformed.
- The rest of the code receives typed values from it, by injection or import; nothing else reads the environment.
- Tests build the configuration object directly instead of setting environment variables.

## Classify every setting

| Class | Examples | Where it lives | Rules |
| --- | --- | --- | --- |
| Secret | database password, API keys, signing keys, webhook secrets | the secret manager, or the environment injected from it | Never in the repository, logs, error messages, or build output; rotatable without a code change |
| Environment configuration | hostnames, URLs, pool sizes, feature flag defaults per environment | the environment or deployment configuration | Differs per environment; validated at start-up |
| Build configuration | target platform, bundler mode, compile-time flags | build files in the repository | Fixed per artifact; never read at run time from the environment |
| Constant | page size limits, retry caps, the product's names | code | A reviewed change, not a knob |

When in doubt, classify it as a secret. Moving a value out of the secret manager later is easy, and a leaked value cannot be taken back. Anything that grants access, signs, or decrypts is always a secret. Public values bundled into a client (a browser or mobile app) are never secrets, whatever they are called.

## Enforce it with a lint rule

Ban direct environment access everywhere except the boundary module, with the linter the project already runs:

- Python (Ruff): `flake8-tidy-imports` banned APIs (`TID251`) for `os.environ` and `os.getenv`, with a per-file ignore for the config module.
- JavaScript and TypeScript (ESLint): `no-restricted-properties` on `process.env` (and `import.meta.env`), with an override for the config file.
- Go: `forbidigo` on `os.Getenv` and `os.LookupEnv`, excluded for the config package.
- Other stacks: a static-analysis rule, such as a Semgrep rule, that matches environment reads outside the config path.
