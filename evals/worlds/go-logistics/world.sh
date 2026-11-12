#!/usr/bin/env bash
set -euo pipefail
# A small shipping-label tool in Go, in a repository that uses aidd under the solo profile. It prints a parcel's label line,
# and its one test passes. The files are ours and are written only inside the case's workspace.
mkdir -p .aidd
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: solo
YAML
cat > go.mod <<'GO'
module example.com/labels

go 1.22
GO
cat > label.go <<'GO'
package main

import "fmt"

// Label is the line printed on a parcel: its tracking code and its weight in grams.
func Label(code string, grams int) string {
	return fmt.Sprintf("%s %dg", code, grams)
}
GO
cat > label_test.go <<'GO'
package main

import "testing"

func TestLabelNamesTheCodeAndTheWeight(t *testing.T) {
	if got := Label("PK-1", 250); got != "PK-1 250g" {
		t.Fatalf("got %q", got)
	}
}
GO
cat > main.go <<'GO'
package main

import "fmt"

func main() {
	fmt.Println(Label("PK-1", 250))
}
GO
git init -q -b main .
git config user.name "Eval Person"
git config user.email "eval@example.com"
git add -A && git commit -q -m "feat: parcel label"
