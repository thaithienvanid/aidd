## Summary

<!-- What changes and why, for reviewers. -->

```toml aidd
route = "minor"
type = "fix"
# spec = "specs/SPEC-123.md"   # a Spec-lane change: keep only this line, uncommented, with your Spec's path
```

<!--
The default is a minor, fast-lane change: set `type` (feat, fix, docs, ...), or run `aidd describe` to print
the block for your branch. A change that needs a Spec (normal or major) keeps only the `spec` line.
Standard and emergency changes use the inline forms in .agents/skills/aidd/assets/change-request.md.
The aidd/gate status derives tests, approvals, and scope from the platform; do not paste results here.
-->
