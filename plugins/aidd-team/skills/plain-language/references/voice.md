# Voice: clear, and still natural

Load this when you write or review prose a person reads, at any level but `ste-100`. Short sentences alone don't make text easy to read. Text reads like a manual when every sentence has the same shape and nothing links them.

## The rules

- Talk to the reader who acts as "you". Say "a person" or "human" only in a normative rule, or where a person is set against an agent.
- Use a colon to introduce a list, an example, or a quote. Never join two clauses with one. Say "so", "because", "then", or "and", or write two sentences.
- Keep asides out of parentheses. Give an aside its own sentence, or cut it. Use one pair of parentheses in a sentence at most.
- Give the reason with the rule, in the same sentence or the next.
- Link the sentences. Say what follows ("then"), what contrasts ("but"), and what results ("so").
- Use "it" or "they" when the noun it stands for is the clear subject just before. Repeat the noun only when two could compete.
- Use verbs, not nouns made from them. Write "approve", not "give approval".
- Mix short sentences with longer ones. A run of sentences of one length reads like a list.
- In `plain` text, contractions are fine: "don't", "it's", "you'll".
- Lead with what the reader gets, and show an example before a definition.
- Read it aloud. Rewrite what a colleague would not say.

Steps, warnings, and rules stay at `ste-80`. Give one instruction in each sentence, so a reader under stress can't misread a step.

## Before and after

> **Like a manual:** Then deploy it. On staging, run `make deploy` (or the pipeline's button): the tests run once more and the release goes out.

> **Natural:** Then deploy it. Run `make deploy`, and the tests run once more before the release goes out.

> **Like a manual:** The step that resets a password: the person opens the link in the email.

> **Natural:** To reset your password, open the link in the email we sent you.

## How to measure it

A project can count two shares on each page. One is the sentences that join two clauses with a colon, and the other is the sentences that hold parentheses. Keep each at 10% or less, and flag a word said twice in a row, as in `the the`. A colon that ends a sentence before a list doesn't count, and neither does a time such as 10:42 or a generated block, whose words come from their source. The rest is for review, so read the page aloud before you hand it off.
