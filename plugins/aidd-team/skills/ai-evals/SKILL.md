---
name: ai-evals
description: "Practice skill: build and prove an AI feature with evals. Use when a Task changes a model call, a prompt, a system prompt, retrieval or RAG, embeddings, an agent, a tool, or a guardrail, or when someone says the model got worse, it hallucinates, the answers are wrong, switch models, prompt injection, jailbreak, eval, golden set, LLM as judge, or it costs too much or is too slow: golden datasets and thresholds before code, versioned prompts and models, injection and safety probes, cost and latency budgets, and eval-based rollback."
metadata:
  checked: "2026-09-25"
---

# AI evals

**Use it when** a Task changes a model call, a prompt, retrieval, embeddings, an agent, a tool, or a guardrail. The `aidd-team:ai-features` and `aidd-team:ai-agents-and-tools` packs say what applies; this skill is how to do the work.

**Do not use when** the change touches no model, prompt, retrieval, or agent behavior; a deterministic function is proved by test-design, and an eval suite there is cost without a signal.

## Standards

- NIST AI RMF 1.0 and AI 600-1.
- OWASP Top 10 for LLM Applications (2026) and for Agentic Applications (2026).
- Evals first with golden datasets.
- Model cards.
- OpenTelemetry GenAI semantic conventions.

## Specify, before Spec approval

- The golden dataset: its size, its source, how it was labeled, and how it stays out of training; the thresholds the change must meet (task accuracy, refusal and safety rates, groundedness for retrieval) and the regression set for behavior it must keep.
- LLM-as-judge only when calibrated against human labels on a sample, with the agreement rate recorded.
- Cost and latency budgets per request; the model, prompt, and parameter versions pinned in the Spec; an injection and jailbreak test set for every untrusted input.

## Implement

- The eval harness runs as a test command in CI; outputs are structured and validated; guardrails and tool allow-lists are code, not prose; prompts and models are versioned as code.
- Every model and tool call is traced with the GenAI conventions, with cost and tokens as attributes; caching and retries are explicit.

## Test commands

- The eval suite with thresholds (promptfoo or Inspect, both emerging, or the repository's own runner); the regression evals; injection probes (garak, emerging, or a promptfoo red-team run); cost and latency thresholds; a PII scan of outputs and logs.

## Review

- Evals green on head, with the numbers in the PR/MR; the model card updated.

## Ship

- A canary with an eval-based and a cost-based rollback trigger; prompts and outputs logged under the privacy rules.

## Hand off

- Done: the change with its eval results against the thresholds. Next: the reviewer and the security engineer. Needs: a threshold the product manager has not set, or labels only humans can provide. Stopped at: none, or the stop rule that fired.
