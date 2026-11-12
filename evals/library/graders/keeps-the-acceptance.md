---
type: regex
pattern: '^---\ntype: spec\nid: "SPEC-4"\ntitle: "Page the order list"\nstatus: approved\napproved_by: "@org\/leads"\napproved_at: "2026-11-02T09:00:00Z"\nchange_type: "feat"\nroute: "normal"\nconfidence: high\nopen_questions: \[\]\ntrace_id: "SPEC-4"\nrollback: Revert the change\.\n\nrisk:\n  summary: "The order list shows one page at a time"\n  dimensions: \[\]\n  irreversible: false\n\ntasks:\n  - id: "SPEC-4-T1"\n    title: "Page the list"\n    scope: \["src\/orders\.py"\]\n\ntests:\n  files: \["tests\/test_orders\.py"\]\n  commands:\n    - name: acceptance\n      command: \["python3", "-m", "unittest", "tests\.test_orders"\]\n      new_behavior: true\n      covers: \[A1\]\n---\n\n## Request\n\n"The order list is too long\. Show it a page at a time\."\n\n## Acceptance\n\n- A1: given 250 orders, when the list is asked for page 1, then it returns 100 orders\.\n(?![\s\S])'
target:
  source: file
  path: specs/SPEC-4.md
---
