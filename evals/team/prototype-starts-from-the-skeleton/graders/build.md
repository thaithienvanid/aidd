---
type: llm
---

PASS if the agent does all of these:

- It starts the prototype from the tool's skeleton, with `aidd new design-spec --prototype` or the tool's own command. It keeps the format the skeleton's comment describes.
- It looks at the showcase (`aidd prototype --example`) for the format and the finish. It copies none of its screens, copy, or data.
- Each screen of the flow is a `data-screen` section. It has the states it can be in, such as empty, loading, error, and success.
- Each state is reachable, with real copy and no lorem ipsum.
- Every control has a `data-testid`, every move between screens is a `data-go`, and the data sits in the fixtures block.
- It opens or checks the file with `aidd prototype`. It tells the person the command and the deep link to a view.

FAIL if the agent copies the showcase as its start, or writes its own viewer or a script into the design file. It also fails if it leaves a state unreachable, adds a network call or a build step, or never runs `aidd prototype` on the file.
