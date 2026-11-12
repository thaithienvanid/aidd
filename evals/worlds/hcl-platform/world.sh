#!/usr/bin/env bash
set -euo pipefail
# A small infrastructure repository written in HCL, the language Terraform reads, in a repository that uses aidd under the solo profile. It declares one
# storage bucket. The files are ours and are written only inside the case's workspace.
mkdir -p .aidd
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: solo
YAML
cat > main.tf <<'TF'
resource "aws_s3_bucket" "assets" {
  bucket = "example-assets"
}
TF
printf '# Platform\n\nThe bucket the web app serves its assets from.\n' > README.md
git init -q -b main .
git config user.name "Eval Person"
git config user.email "eval@example.com"
git add -A && git commit -q -m "feat: assets bucket"
