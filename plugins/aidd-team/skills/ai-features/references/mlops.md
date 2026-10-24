# MLOps: a model you train yourself

Load this when a change trains, fine-tunes, or ships a model of the team's own, not only a call to a hosted model. The evals that prove a model good enough are `aidd-team:ai-evals`. This file covers what makes a model version reproducible, traceable, and safe to roll back.

## A model registry with versioned artifacts

- Every model that can reach production is a registry entry with a version, never a file on a shared drive.
- Each version records the training code's commit, the data snapshot's ID and hash, the hyperparameters, the environment lock, and the eval results, with the eval set's version.
- A version moves through stages, such as candidate, staging, and production, and each promotion is a change with its evals in the Spec. Nobody promotes a version by hand outside the loop.
- The serving config names the model version exactly, so a rollback is a change of one value back to the previous version.

## Reproducible training

- Training reads a pinned data snapshot, never "the latest table".
- It pins the seeds, the library versions, and the base image. Where the hardware makes a run nondeterministic, the Spec says so and sets the tolerance a rerun must meet.
- A rerun from the recorded inputs produces a model whose eval results fall within that tolerance. That rerun is the reproducibility test, and it runs before a version is promoted.

## Drift as an observe signal

A model degrades without a code change. Its inputs shift, or the world it predicts changes.

- **Input drift:** the distribution of each important feature against the training snapshot's.
- **Prediction drift:** the distribution of the model's outputs over time.
- **Outcome quality:** the eval metric on labelled outcomes as they arrive, which is the signal that matters most.

Each has a threshold in the observe block. Crossing it is a rollback trigger or a retraining Task, and the Spec says which.

Source: [Google Cloud, MLOps: continuous delivery and automation pipelines in machine learning](https://cloud.google.com/architecture/mlops-continuous-delivery-and-automation-pipelines-in-machine-learning), last updated 2024-08-28, read 2026-10-22.

## Training data you may use, and a general-purpose model you ship

- Each data snapshot records where its data came from, under which licence or terms, and whether a rights holder opted out of text and data mining. A snapshot with an unknown source never trains a model that ships.
- In the EU, a team that places a general-purpose AI model on the market is its provider. So is a team that modifies one enough to become its provider. From 2025-08-02 the provider keeps technical documentation, a copyright policy, and a public summary of the training content (AI Act Art. 53). Name the role in the Spec, and keep these with the model's registry entry.

Source: [Regulation (EU) 2024/1689, as amended by Regulation (EU) 2026/1744](https://eur-lex.europa.eu/eli/reg/2024/1689/oj), read 2026-10-22.
