#!/usr/bin/env bash
set -euo pipefail
# A small package in JavaScript, in a repository that uses aidd under the solo profile. It pads a number with zeros, and its
# one test uses Node's own runner. The files are ours and are written only inside the case's workspace.
mkdir -p .aidd src test
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: solo
YAML
cat > package.json <<'JSON'
{
  "name": "pad-number",
  "version": "1.0.0",
  "type": "module",
  "scripts": { "test": "node --test" }
}
JSON
cat > src/index.js <<'JS'
export function pad(number, width) {
  return String(number).padStart(width, "0");
}
JS
cat > test/index.test.js <<'JS'
import { test } from "node:test";
import assert from "node:assert/strict";
import { pad } from "../src/index.js";

test("pad fills the width with zeros", () => {
  assert.equal(pad(7, 3), "007");
});
JS
git init -q -b main .
git config user.name "Eval Person"
git config user.email "eval@example.com"
git add -A && git commit -q -m "feat: pad"
