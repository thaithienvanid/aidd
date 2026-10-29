---
id: postgres/pgvector
type: opinionated
fills: [ai-features:vector-store]
default: true
implements: ai-features:Implement
roles: [developer, architect, reviewer]
when_changed: ["migrations/**", "**/*.sql", "**/*embedding*", "**/*retriev*"]
why: "pgvector keeps the embeddings in the PostgreSQL database that holds the rows they describe, so one backup, one access control, and one transaction cover both, and no second database bills or fails."
reviewed: "2026-10-22"
maturity: established
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: [the host's managed vector search, Qdrant, Weaviate, Milvus, Pinecone]
status: active
source: https://raw.githubusercontent.com/pgvector/pgvector/master/CHANGELOG.md
evidence: "## 0.8.7 (2026-10-01)"
---

# pgvector stores and searches the embeddings in PostgreSQL

It answers the vector-store choice of `aidd-team:ai-features`. pgvector is under the PostgreSQL License, and Amazon RDS, Cloud SQL, Azure Database for PostgreSQL, and Neon offer it.

## What pgvector supports

As read on the `checked` day: the newest release is 0.8.7, which fixed a buffer overflow in IVFFlat index builds. A managed service ships its own pgvector release, often an older one. Iterative index scans, which stop a filtered query from returning too few rows, need 0.8.0 or later.

## What the team does

- Turn it on in a migration (`CREATE EXTENSION IF NOT EXISTS vector`), and record the extension's version in the Spec.
- Store each embedding beside the name and version of the model that made it, in a column sized to that model's dimensions. Re-embed every row in a change of its own when the model changes.
- Use `halfvec`, which halves the storage, once the retrieval eval shows no loss of recall.
- Build an HNSW index with the operator class of the model's distance, such as `vector_cosine_ops`. On a live table, build it `CONCURRENTLY`, with enough `maintenance_work_mem`.
- Turn on `hnsw.iterative_scan` for a query that also filters, such as by tenant.
- Set `hnsw.ef_search` from the recall the eval measures, not from a guess.
- Move to a dedicated vector database only when the measured latency or the corpus size passes what the Spec allows.

## What the gate runs

Nothing of its own. The eval suite of `aidd-team:ai-evals` measures the recall.
