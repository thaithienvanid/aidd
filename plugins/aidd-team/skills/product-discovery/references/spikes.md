# Spikes for the riskiest assumption

Load this when the assumption map names a risky assumption that has little evidence.

## Link it or accept it

The riskiest, least-evidenced assumption gets one of two entries on the assumption map:

- A link to a spike exploration, such as `docs/architecture/explore/<topic>/`.
- The words "accepted without a spike", with the person who accepted the risk and the reason.

Never leave the entry blank. A blank entry hides a risk that nobody chose to take.

## Run a spike

1. Start it: `aidd new exploration docs/architecture/explore/<topic> --title "<the question>" --owner architect --timebox <end date>`. For a spike, the timebox is a date (YYYY-MM-DD).
2. Write one question that the spike can answer. If it compares two or three options, write each one as a direction.
3. Build the least code that answers the question. Spike code is thrown away. It never merges as product code.
4. When the timebox ends, stop. Put the results in the folder or at a link, and list them in `evidence`.
5. A person records the outcome: `outcome = { decision = "adopted", by = "@lead", on = 2026-10-17 }`. The decision is adopted, rejected, or inconclusive. Then set `status = "decided"`.

`aidd validate` warns when the timebox date has passed and the spike has no outcome.

## After the outcome

- Adopted: the assumption has evidence now, and the next Spec builds on it. Record a design choice in an ADR.
- Rejected: go back to the opportunity solution tree and pick the next candidate solution.
- Inconclusive: run a smaller spike, or a person accepts the risk without a spike.
