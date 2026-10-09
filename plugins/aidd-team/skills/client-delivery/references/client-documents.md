# Client documents

Load this before you send a proposal, a contract, a change order, a status report, or release notes to a client. Write them at the `plain` level (`aidd-team:plain-language`).

## Nothing misleading

Do this pass before sign-off. Read each sentence as the client will read it, and fix each claim that the evidence does not support.

| Claim | What it needs |
| --- | --- |
| An absolute word: "every", "same", "never", "already works" | Matching evidence for the word. If the evidence covers less, write what it covers. |
| "It works on the device" | A test on a real device. A result from a simulator or an emulator is not a real-device result; say which it is. |
| "Same as X" | The exceptions, named. If there are none, say that you checked. |
| A date that a third party controls | The third party's own statement, cited: a store review time, a vendor's release date, or a regulator's deadline. |

## Dates

- Give two dates when the client must plan around one. The likely date is the date you expect. The committed date is the date you promise.
- Say what the contingency between them covers: the named risks, the external waits, and the client's own tasks. A contingency that covers nothing named is padding.
- A committed date moves only by a change order (`aidd new contract`).

## Already decided for you

List the decisions the team made for the client, each with its reason: the hosting, a library, a default, or a limit. The client can see what they did not choose. They can then ask to change it before the work starts, when a change costs less.

## Numbers live once

Each number lives in one document: a price, a date, an estimate, or a support level. Other documents link to it and never restate it. A restated number drifts when the source changes, and the client then holds two answers.

## An explainer deck, on request

On request, build a deck or an explainer page from the source documents. It helps a client see the change.

- Make it a single HTML file in the style of 3Blue1Brown: one idea per slide, and the picture built up step by step.
- Show before and after for each change.
- Write the captions at the reader's level.
- Make it readable in light and dark, and make it print to PDF.
- It is disposable. The source documents stay the record. The deck is never the record and never evidence.
- Build it again from the sources when they change. Never edit the deck to change a fact.
