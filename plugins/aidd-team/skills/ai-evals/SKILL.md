---
name: ai-evals
description: "Practice skill: prove an AI feature with evals. Use in an aidd repository when a Task changes a prompt, model call, RAG, agent, or guardrail, or answers got worse."
metadata:
  checked: "2026-10-22"
---

# AI evals

**Use it when** a Task changes a model call, prompt, retrieval, embeddings, an agent, a tool, or a guardrail. The `aidd-team:ai-features` and `aidd-team:ai-agents-and-tools` packs say what applies. This skill is how, and it owns the eval tests both packs point to.

**Do not use when** the change touches no model, prompt, retrieval, or agent behavior. There, test-design proves a deterministic function.

## Standards

<!-- aidd:gen practice:ai-evals -->
| Standard | Edition | Checked | Source |
| --- | --- | --- | --- |
| Evals with golden datasets, and model cards | — | 2026-10-16 (reviewed) | — |
| The ML Test Score (Breck et al., IEEE BigData 2017) | — | 2026-10-16 (reviewed) | <https://research.google/pubs/pub46555/> |
| Evaluation beyond accuracy: calibration, robustness, and bias and fairness testing against a stated bias taxonomy, with the results in the model card | NIST SP 1270 | 2026-10-16 | <https://doi.org/10.6028/NIST.SP.1270> |
| Adversarial ML taxonomy for red-team probes and injection and jailbreak defences, with MITRE ATLAS techniques mapped to the eval suite | NIST AI 100-2 E2025 | 2026-10-16 | <https://csrc.nist.gov/pubs/ai/100/2/e2025/final> |
| Cost and latency budgets per request, measured in evals | — | 2026-10-16 (reviewed) | — |
| Retrieval and agent evaluation: RAG metrics (faithfulness, context and answer relevance) and tool-use trajectory evals, per the published agent-design guidance (emerging) | — | 2026-10-16 (reviewed) | <https://docs.ragas.io/> |
| Eval statistics: a confidence interval on every score, and pass^k for reliability over repeated trials (emerging) | arXiv 2411.00640 (2024); pass^k from τ-bench, arXiv 2406.12045 | 2026-10-16 | <https://arxiv.org/abs/2411.00640> |
| OWASP AI Testing Guide (emerging) | v1 | 2026-10-22 | <https://owasp.org/www-project-ai-testing-guide/> |

### Open choices

The team decides these. aidd's default holds until a `standards` entry fills one (`aidd standard list`).

| Choice | Question | aidd's default | Options |
| --- | --- | --- | --- |
| `eval-runner` | Which runner runs the eval suite on each change? | DeepEval in a Python project and promptfoo in a TypeScript one, pinned, with telemetry off. Inspect where the agent's path is scored, not only its answer. | DeepEval, promptfoo, Inspect, the repository's own runner |
<!-- aidd:end -->

## Specify

- Write the eval first. Before Spec approval, the verifier adds the golden case that fails on the base commit, and the prompt or model change turns it green.
- The golden dataset: size, source, how it was labeled, and how it stays out of training. The thresholds the change must meet (task accuracy, refusal and safety rates, groundedness for retrieval) and the regression set for behavior it must keep.
- Every score has its 95% confidence interval and a set large enough for the decision. Use pass^k for anything that varies by run. Contamination, judges, slices, and what to score: [references/statistics.md](references/statistics.md).
- Use LLM-as-judge only when calibrated against human labels on a sample, the agreement rate recorded.
- Give cost and latency budgets per request. Each untrusted input gets an injection and jailbreak test set. Past the golden set, take the trustworthiness tests the change needs from the OWASP AI Testing Guide.

## Implement

- The eval harness runs as a CI test command. Structure and validate outputs. Guardrails and tool allow-lists are code, not prose. Version prompts, models, and the golden set as code.
- Trace every model and tool call with the GenAI conventions, cost and tokens as attributes. Make caching and retries explicit.

## Review

- Evals are green on head, with the numbers in the PR/MR.

## Roll out

- Turn each production regression into a golden case, and sample live traffic into the golden set. Plan each pinned model's retirement: [references/statistics.md](references/statistics.md).

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Eval suite (emerging) | the golden-dataset thresholds hold on head | the eval-runner's `tests` entry, such as Inspect, DeepEval, or promptfoo, with thresholds |
| Regression evals | kept behavior did not move | the same runner on the previous golden set |
| Repeated-trial reliability | pass^k meets its threshold | k repeats per item, such as k: 5: Inspect `--epochs 5 --epochs-reducer pass_k_5`, DeepEval `-r 5`, or promptfoo `--repeat 5` scored as all five passing |
| Injection probes (emerging) | prompt injection and jailbreak probes are blocked; for an agent, an instruction in each untrusted input reaches no tool | `uvx garak==0.17.0`, or the eval-runner's red-team run, such as promptfoo's |
| Cost and latency budget | each request stays within the budget | the eval runner's cost and latency metrics, with thresholds |
| Output PII scan | no personal data in the eval outputs | Presidio (`presidio-analyzer` 2.2.364) over the eval outputs, failing on a finding over the threshold |

## Stop if

- A threshold or the golden dataset is missing, so nothing can fail.
- An LLM judge scores the change with no recorded agreement rate against human labels.
- An untrusted input has no injection probe, or a model, prompt, or parameter is not pinned.

## Hand off

- Done: the change with its eval results against the thresholds. Next: the reviewer and the security engineer. Needs: a threshold the product manager has not set, or labels only humans can provide. Stopped at: none, or the stop rule that fired.
