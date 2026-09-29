# Org rules as policy as code (OPA/Rego), run by the aidd Policy interface.
# Bind it in .aidd/config.toml:
#   [interfaces]
#   policy = ["./scripts/aidd-policy-opa"]
# The wrapper script (aidd-policy-opa, next to this file) evaluates `data.aidd.answer`
# against the change in $AIDD_INPUT_FILE and prints the JSON the gate reads.
package aidd

import rego.v1

# Freeze every route but incident during the listed release windows (UTC dates).
freeze_days := {"2026-12-24", "2026-12-31"}

today := substring(time.format([time.now_ns(), "UTC", "2006-01-02"]), 0, 10)

frozen if {
	today in freeze_days
	input.route != "incident"
}

# Payments changes must link a PAY- ticket in the PR description.
findings contains finding if {
	some path in input.paths
	startswith(path, "src/payments/")
	not regex.match(`PAY-[0-9]+`, input.body)
	finding := {
		"rule": "payments-ticket",
		"level": "fail",
		"message": sprintf("%s changes payments, but the description links no PAY- ticket", [path]),
		"fix": "add the PAY- ticket to the PR description",
	}
}

# Changes to generated clients are allowed, but reviewers should know.
findings contains finding if {
	some path in input.paths
	startswith(path, "clients/generated/")
	finding := {"rule": "generated-client", "level": "warn", "message": sprintf("%s is generated; regenerate instead of editing", [path])}
}

default verdict := "allow"

verdict := "freeze" if frozen

answer := {"verdict": verdict, "findings": findings, "detail": "org policy v1"}
