+++
id = "typescript/zod-validation"
type = "opinionated"
fills = ["apis-and-services:validation-library"]
default = true
implements = "apis-and-services:Schema conformance"
roles = ["developer", "architect", "reviewer"]
when_changed = ["**/*.ts", "**/*.tsx", "package.json"]
why = "One Zod schema checks the input at run time and gives its TypeScript type, and the same schema can write the OpenAPI document, so the check, the type, and the contract never drift."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "established"
tool = { name = "zod", registry = "npm", package = "zod" }
version_policy = "current_major"
checked_version = "4.6.5"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
source = "https://registry.npmjs.org/-/package/zod/dist-tags"
evidence = '"latest":"4.6.5"'
alternatives = ["Valibot", "JSON Schema with Ajv", "ArkType"]
status = "active"
enforced_by = [
  { name = "major", command = ["node", "-e", "process.exit(require('./node_modules/zod/package.json').version.startsWith('4.') ? 0 : 1)"] },
]
+++

# Zod validates input at the boundary

It answers the validation-library choice of `aidd-team:apis-and-services`.

## What the team does

- Parse every request body, query, header, and message with a Zod schema where it enters the service, then pass on the parsed value only.
- Derive the TypeScript type with `z.infer`; never write the type a second time by hand.
- Use `safeParse` at the boundary and answer a failure with the service's error format. Never echo the raw input back.
- Keep each schema strict (`z.strictObject`), so an unknown field is refused rather than passed through.
- Validate the environment at startup with a schema too, so a missing setting stops the process.

## What the gate runs

One `[[tests]]` entry checks that the project resolves the major release this standard was checked at, so an upgrade is a reviewed change.
