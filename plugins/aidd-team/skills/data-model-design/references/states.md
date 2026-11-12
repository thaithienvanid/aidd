# States, events, sets of values, and what comes after

Load this when a Task adds or changes an object whose state changes after it is written: an order, a ticket, a loan, a job, an account. Load it too when a Task adds a status, a code, a value to an enum, or a reminder, or when something must happen after an object is finished. The ids in brackets are the standards in the skill's table. A rule with no id is common practice that the standards do not state.

## Four kinds of thing

A model that changes over time holds four kinds of thing. Keep them apart, because a reader who takes one for another writes the wrong thing.

| Kind | What it is | Who writes it | In a library's loans |
| --- | --- | --- | --- |
| A state | the object's place in its life, stored on the object | the system, when an event arrives | `on_loan`, `returned`, `lost` |
| An event | a fact that happened, at a time | whoever saw it happen | the book came back on 3 March |
| An action | what a caller asks for | a person or a client | renew this loan |
| A derived view | an answer computed when it is read | nobody, because it is never stored | overdue: on loan, and past its due date |

`aidd-team:naming` gives each kind its written form (`references/across-media.md`, "Names in a data model").

- A state is stored, and an event moves it. The state field is the system's to write: a caller asks for an action, and never sets the state. [aip-216]
- A derived view is not a state. Never list it among the values of a state field, and never store it. Three stored values only look derived: a cache with its rebuild rule, a term that is fixed when it is written, and a state beside the facts of the event that moved it. Say in its description what it reads. A reader of "overdue" reads the due date and today's date, so no writer has to remember to set it.
- A state field is all stored or all derived. When a person writes some values and the system computes the others, nobody can tell which ones to write. Split it into the stored state and a view beside it.
- An event may keep its own facts, such as when it happened (`returned_at`) and who caused it. Store the ones that a reader needs. The state says where the object is now. They are different facts, so both may be stored.
- A yes-or-no that records an event is its thinnest record, because it cannot say when or who. Store the event's own facts, as an instant (`shipped_at`) or as an object (`shipped: {at, by}`), and read the yes or the no from their presence. A setting that a person chooses, such as `wants_newsletter`, is no event, so it stays a yes-or-no.

## The state table

Write one table for each object that has a state. Put it in the Spec's Design, or in the format's reference. It is this step's required output.

| State | The event that moves it here | Who causes the event | What comes next, and who does it |
| --- | --- | --- | --- |
| `on_loan`, the first state | the desk checks the book out | staff | the member returns it or renews it |
| `returned`, final | the desk checks the book in | staff | nothing |
| `lost`, final | the member reports it, or 60 days pass after the due date | staff, or the nightly job | nothing on the loan; the same event writes a replacement fee |

- Every value of the state field has a row. Every row names an event that a person or a program can observe. The one who causes the event is a person or a job. The system still writes the field. A state that nothing moves into is dead. A state with no way out is a trap, unless it is final.
- A date may end a state with no event, as an expiry does. Store that move when something else is written or sent because of it, as the fee is for a lost book. Where nothing else changes, read that end as a view, and name the one state it ends so that it claims nothing the date can undo.
- Mark the first state and each final state.
- Where the event is a person's decision, such as an approval, an acceptance, or a release, say who may write the fact, and what enforces that. A plain field that anyone can write enforces nothing, because a record never attests to itself (`data-model-design.md`, "Flow and trust").
- A state the object rests in is an adjective or a past participle, such as `active` or `returned`. A state that ends without anyone acting is a present participle, such as `shipping`. [aip-216]
- Keep the table as small as the truth. An object with two states has two rows. An object with no state has no table.
- Where the project has several types with states, keep one cross-type table of every state word, while the table above is for one object. Give each word one meaning, use the same word for the same state, and hold the set with a schema or unit test.

### Walk the hard cases

A table that shows only the way things go right is not checked. Walk each state field through the cases below. Walk each status that is read from an object's parts too, such as "every line is shipped". Write one line for each case that applies: what the state reads, and what comes next. A plain view of one object's own fields needs no walk.

| Case | The question |
| --- | --- |
| A step fails | Where does the object rest, and who sees it? |
| A person cancels | Which state does it reach, and what happens to the work under it? |
| A step is undone | A release is rolled back, or a payment is refunded. Does the object still read as finished? |
| Nobody acts | Does it wait for ever, and who is told? |
| The set is empty | A status that reads "every part is done" is true at once for an object with no parts. Is that right? |
| A part ends another way | One part is cancelled, or it fails. Is the whole stuck, or finished? |
| Old records | An object was written before this change. What does it read now? |

An order that is `fulfilled` when every line is shipped fails three of them. An order with no lines is fulfilled at once. A cancelled line stops it for ever. A returned line still reads as shipped. A new rule that reads the state from new fields fails the last case, when last year's orders hold only the old field.

## A set of values

- A set of values, such as an enum or a list of codes, answers one question, and every value in it is one kind of thing. Read the whole set each time you add a value. Does the new value complete the same sentence as the others? A set that holds a state, an action, and a date that passed is three sets.
- Ask whether the set should exist. A value that other stored fields already decide is a derived view, so the set is a second vocabulary for one fact. A set that gains values often is not an enum, because each new value may break a reader. Use a string with a stated format, or expose the separate facts that the readers need. Size alone is no finding: a list of currency codes is long and sound. [k8s-api-conventions, aip-180]
- A value that joins two facts makes the set the product of two smaller ones. `data-model-design.md`, "Structure", has the tests for when to split it.
- Say in each enum's description whether it is closed or may grow. [aip-216]

## After a final state

When an object reaches a final state, nothing more is asked of it, and its state never says that something is owed. A finished object may still gain a fact about itself. It never gains a state. What comes later takes one of three shapes, by what it is.

| What comes later | Its shape | Example |
| --- | --- | --- |
| A fact about the finished object that arrives with nobody acting on the object: a system records it, or its absence is only reported | Store the fact as an event of its own. List the objects that lack it as a view | A delivered shipment stores `signed_at` when the customer signs. The depot's list is every shipment delivered ten days ago or more with no signature |
| A rule that the system applies to many finished objects | One rule and one job, and no item for each object | Paid invoices are purged seven years after `paid_at` |
| Work that a person or an agent must still do, or work with its own owner and its own outcome | A new item, written in the change that records the event. It holds a link back to its cause, the day it starts, and its own owner and state | A clinic calls each patient 30 days after a visit, and records what the patient said |

- The first shape is right only when nobody has to act on the finished object to get the fact. Where someone must still act, as when an agent reads a number or a person approves a result, choose one of two. The object is not finished yet, and it stays open until that is done. Or the work is a new item with its own owner.
- The smell is a reminder, derived on a finished object, that a person or an agent must answer and that nothing but the finished object records. A view that finds work which is then written as an item of its own is no smell. Neither is the check for a missing item, in a bullet below.
- Never give a finished object a state, a code, or a flag that means "something is still owed". A reader can then no longer tell whether it is finished. A list that hides finished work also hides what that work still owes.
- Reopen an object only to correct a mistake: it was closed, and that was wrong. Issue trackers keep "reopened" for this one case.
- A new item costs a write, and someone can forget it. Where a second path can record the event without the item, add a check that finds a missing one.
- A date on an object that is still open stays a field with a derived reminder, as a subscription's renewal date does. That reminder cannot be forgotten, and it follows a corrected date.

## Check

- Each state field has its state table, and each value has a row.
- Each state field, and each status read from an object's parts, has its line for every hard case that applies.
- Each fact that a person's decision writes says who may write it, and what enforces that.
- No derived value is stored or listed as a state, and each view says what it reads.
- Each set of values answers one question, holds one kind of thing, and says whether it may grow. An older set that gains a value is read whole, with its old values.
- No final state has a step after it, except the correction of a mistake, and nothing on a finished object means that work is owed.
- Each thing that comes after a final state has one of the three shapes. It is a fact with its view, one rule and one job, or a new item with a link, a start day, and an owner. A fact with its view is used only where nobody must act on the finished object to get the fact.
- Across types, one cross-type table holds every state word with one meaning each, enforced by a schema or unit test.
