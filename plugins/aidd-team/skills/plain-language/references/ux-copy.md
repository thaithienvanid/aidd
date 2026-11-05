# UX copy, state by state

Load this when you write the words on a screen: a label, a button, an empty state, an error, a confirmation. The design spec names each screen's states; this page says what each one's copy does.

## Voice

The voice comes from the design system, never from this page. `DESIGN.md` names it (formal or plain, "you" or "we", how warm). With no `DESIGN.md` yet, use plain, direct, and calm, and say so in the design spec as an assumption.

- One word for one thing on every screen: the glossary's term, as the product's people say it.
- A control names its action as a verb and its object: "Save draft", never "OK" or "Submit".
- Unless `DESIGN.md` says otherwise: sentence case, no exclamation marks, no blame ("you entered an invalid"), no internal names (codes, table names, a team's jargon).

## Each state

| State | The copy does | It never |
| --- | --- | --- |
| Empty, first use | says what will be here and the one action that fills it | says "No data" or shows a bare zero |
| Empty, no results | says what was searched and how to widen it | reads like first use: "You have no items yet" after a search |
| Loading | is mostly silent; past about a second, says what is happening | promises a time it cannot keep |
| Partial | says what is shown and what is missing, and why if known | hides the gap |
| Error | says what happened, in the person's words, and what to do next; keeps what they typed | shows a code alone, or "Something went wrong" with no next step |
| Offline | says what still works and what waits until the connection is back | blocks everything with one message |
| Permission denied | says who can grant it, or how to ask | says only "Access denied" |
| Success | confirms the result and the next likely step, briefly | celebrates a routine action |
| Validation | sits by the field, says the rule before the person breaks it, and how to fix it | waits for submit, or lists every rule at once |

An error answers each problem type the API returns, one message each, written in the design spec beside the state. The API's own `detail` is shown only where the API writes it for people, in their language.

## A contrast pair

A search screen with no results:

- **Weak:** "No results." The person cannot tell whether the search worked, whether the data is empty, or what to try next.
- **Strong:** "No `<items>` match `<the search, in the person's words>`. `<Widen it>`, or `<find them another way>`." It names what was searched, implies the data exists, and gives two actions, each a control on the screen.

Illustrative, from three unrelated products: "No invoices from March over 500 EUR. Clear the amount, or pick another month." "No flights to Lisbon on 12 May. Try the next day, or a nearby airport." "No sitters within 5 km on Saturday. Widen the distance, or pick another day."

The line that tells them apart: the strong one names the person's own input and the next step.

## Check it

- Read every state's copy aloud with the screen's title before it. Each reads as one sentence a person would say.
- Every action the copy names is a control on that state.
- The copy passes the plain-language rules: sentences of 35 words or fewer, active voice, one term for one thing.
- Real copy at realistic lengths, in the longest language the product ships, fits without truncation at 320 CSS pixels and at text 200%.
