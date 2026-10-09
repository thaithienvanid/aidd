+++
id = "cost/pr-cost-delta-threshold"
type = "opinionated"
fills = ["cloud-and-infrastructure:cost-estimate-tool"]
default = true
implements = "cloud-and-infrastructure:Cost diff threshold"
roles = ["platform-engineer", "architect", "reviewer"]
when_changed = ["**/*.tf", "**/*.tofu", "**/*.tfvars", "infracost.yml"]
why = "Infracost prices the plan of the base and of the change before the merge, so a change that raises the monthly cost past the threshold fails until its Spec names the increase."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "emerging"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
alternatives = ["the provider's pricing calculator, with the estimate in the Spec"]
status = "active"
source = "https://www.infracost.io/docs/features/cli_commands/"
evidence = "The CLI auto-detects the IaC type (Terraform, Terragrunt, CloudFormation, etc.) from the directory contents."
enforced_by = [
  { name = "delta", command = ["python3", "-c", "import json,os,sys;m=os.environ.get('COST_MAX_INCREASE') or sys.exit('set COST_MAX_INCREASE to the team threshold, a percent of the base monthly cost');b,h=(float((json.load(open(p)).get('summary') or {}).get('total_monthly_cost') or 0) for p in sys.argv[1:3]);print(f'monthly cost: base {b:.2f}, head {h:.2f}, allowed increase {m} percent');sys.exit(1 if h-b>b*float(m)/100 else 0)", "infracost-base.json", "infracost-head.json"] },
]
+++

# The cost diff of a change fails above the team's threshold

It answers the cost-estimate-tool choice of `aidd-team:cloud-and-infrastructure`, with Infracost, the pack's default, at the version its Cost diff threshold row names.

## What the team does

- In CI, run `infracost scan <dir> --json > infracost-base.json` on the base, and `infracost scan <dir> --json > infracost-head.json` on the change. The check reads `summary.total_monthly_cost` from each file.
- Authenticate with `INFRACOST_CLI_AUTHENTICATION_TOKEN`, a service account token kept in the CI secrets.
- Set `COST_MAX_INCREASE` in the CI environment. It is the team's threshold, a percent of the base monthly cost. aidd sets no value, and the check fails until the team does.
- Raise the threshold only in a reviewed change to the CI configuration, with the reason.
- Know what the scan sends: resource parameters go to Infracost's pricing API, or to a self-hosted endpoint where the company requires one.
- For a resource Infracost does not price, such as most Cloudflare products, write the estimate from the provider's pricing page in the Spec, with the day it was read.

## What the gate runs

One `[[tests]]` entry compares the two scans. A head cost above the base by more than `COST_MAX_INCREASE` percent fails the change.
