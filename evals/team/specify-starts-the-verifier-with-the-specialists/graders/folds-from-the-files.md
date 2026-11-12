---
type: llm
---

PASS if each specialist that ran wrote its return to `.aidd/returns/SPEC-1/<role>.md` and named that path on its handoff note. On this major Spec, those are the security engineer and the SRE. The architect folded the Spec from those files, and the reply says where they are.
FAIL if a return lives only in a chat message or in a folder outside the workspace, such as /tmp. FAIL too if the lead reads a subagent's transcript to recover a return, or asks a role to write it again.
