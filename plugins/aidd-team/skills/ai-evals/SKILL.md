---
name: ai-evals
description: "Practice skill: prove an AI feature with evals. Use in an aidd repository when a Task changes a prompt, model call, RAG, agent, or guardrail, or answers got worse."
metadata:
  checked: "2026-09-30"
---

# AI evals

**Use it when** a Task changes a model call, prompt, retrieval, embeddings, an agent, a tool, or a guardrail. The `aidd-team:ai-features` and `aidd-team:ai-agents-and-tools` packs say what applies. This skill is how to do the work. It owns the eval tests both packs point to.

**Do not use when** the change touches no model, prompt, retrieval, or agent behavior: test-design proves a deterministic function, and an eval suite there is cost without signal.

## Standards

<!-- aidd:gen practice:ai-evals -->
| Standard | Edition |
| --- | --- |
| Evals with golden datasets, and model cards | — |
| NIST AI RMF and the Generative AI Profile (NIST AI 600-1) | AI RMF 1.0; NIST AI 600-1 |
| OWASP Top 10 for LLM Applications | 2026 edition |
| OWASP Top 10 for Agentic Applications (emerging) | 2026 |
| Retrieval and agent evaluation: RAG metrics (faithfulness, context and answer relevance) and tool-use trajectory evals, per the published agent-design guidance (emerging) | — |
| OpenTelemetry GenAI semantic conventions (emerging) | — |
| Eval statistics: a confidence interval on every score, and pass^k for reliability over repeated trials (emerging) | arXiv 2411.00640 (2024); pass^k from τ-bench, arXiv 2406.12045 |

Each standard's checked date and source are in the aidd-team roles reference (`references/roles.md` in `aidd-team:aidd-team`), section `aidd-team:ai-evals`.
<!-- aidd:end -->

## Specify

- The golden dataset: size, source, how it was labeled, and how it stays out of training. The thresholds the change must meet (task accuracy, refusal and safety rates, groundedness for retrieval) and the regression set for behavior it must keep.
- Every score has its 95% confidence interval and a set large enough for the decision. Use pass^k for anything that varies run to run. Keep the golden set free of contamination: [references/statistics.md](references/statistics.md).
- Use LLM-as-judge only when calibrated against human labels on a sample, the agreement rate recorded.
- Give cost and latency budgets per request. Pin model, prompt, and parameter versions in the Spec. Each untrusted input gets an injection and jailbreak test set.

## Implement

- The eval harness runs as a CI test command. Structure and validate outputs. Guardrails and tool allow-lists are code, not prose. Version prompts and models as code.
- Trace every model and tool call with the GenAI conventions, cost and tokens as attributes. Make caching and retries explicit.

## Review

- Evals are green on head, with the numbers in the PR/MR. The model card is updated.

## Ship

- Use a canary with eval-based and cost-based rollback triggers. Log prompts and outputs under the privacy rules.
- Sample live traffic into the golden set. Plan each pinned model's retirement: [references/statistics.md](references/statistics.md).

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Eval suite (emerging) | the golden-dataset thresholds hold on head | `npx promptfoo@0.123.1 eval`, `uvx --from inspect-ai==0.3.273 inspect eval`, or the repository's own runner, with thresholds |
| Regression evals | kept behavior did not move | the same runner on the previous golden set |
| Repeated-trial reliability | pass^k meets its threshold | k repeats per item, such as k: 5: Inspect `--epochs 5 --epochs-reducer pass_k_5`, or promptfoo `--repeat 5` scored as all five passing |
| Injection probes (emerging) | prompt injection and jailbreak probes are blocked; for an agent, an instruction in each untrusted input reaches no tool | `uvx garak==0.17.0`, or a promptfoo red-team run |
| Cost and latency budget | each request stays within the budget | the eval runner's cost and latency metrics, with thresholds |
| Output PII scan | no personal data in model outputs or logs | Presidio (`presidio-analyzer` 2.2.364) over the eval outputs |

## Stop if

- A threshold or the golden dataset is missing, so nothing can fail.
- An LLM judge scores the change with no recorded agreement rate against human labels.
- An untrusted input has no injection probe, or a model, prompt, or parameter is not pinned.

## Hand off

- Done: the change with its eval results against the thresholds. Next: the reviewer and the security engineer. Needs: a threshold the product manager has not set, or labels only humans can provide. Stopped at: none, or the stop rule that fired.
