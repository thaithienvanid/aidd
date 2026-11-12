---
type: llm
---

PASS if the reply keeps the spend cap of 1,000 tokens with the harness's own count, in one of two ways.
With a count for each step, it stops after the first role step, which passes the cap. It asks the person once whether to go on. It states the count as a number and names which tokens it counted.
With no count, it says once, at launch, that this harness doesn't report spend per step, so the cap can't stop the run. It then goes on, and writes `unknown` for each step.
FAIL if the reply gives a spend it estimated, such as "about 40k tokens". FAIL if it stops or asks because the spend is unknown. FAIL too if it asks more than once about spend, or says the run stayed under the cap.
