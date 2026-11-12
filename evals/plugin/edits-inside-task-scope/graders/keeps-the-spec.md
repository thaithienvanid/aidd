---
type: regex
pattern: '^---\ntype: spec\nid: "SPEC-5"\ntitle: "Slugs for article titles"\nstatus: approved\napproved_by: "@org\/leads"\napproved_at: "2026-11-02T09:00:00Z"\nchange_type: "feat"\nroute: "normal"\nconfidence: high\nopen_questions: \[\]\ntrace_id: "SPEC-5"\nrollback: Revert the change\.\n\nrisk:\n  summary: "Article URLs use a slug of the title"\n  dimensions: \[\]\n  irreversible: false\n\ntasks:\n  - id: "SPEC-5-T1"\n    title: "Write slugify"\n    scope: \["src\/slug\.py"\]\n\ntests:\n  files: \["tests\/test_slug\.py"\]\n  commands:\n    - name: acceptance\n      command: \["python3", "-m", "unittest", "tests\.test_slug"\]\n      new_behavior: true\n      covers: \[A1\]\n---\n\n## Request\n\n"Give each article a readable URL\."\n\n## Acceptance\n\n- A1: given the title "Hello, World!", when slugify runs, then it returns "hello-world"\.\n(?![\s\S])'
target:
  source: file
  path: specs/SPEC-5.md
---
