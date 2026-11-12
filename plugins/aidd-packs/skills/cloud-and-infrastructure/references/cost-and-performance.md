# Cost and performance: where a workload runs

Read in Specify, when a change adds or moves compute. Every limit below was read from the provider's page on 2026-09-30. This page keeps no prices: read each one on the provider's pricing page on the day you write the estimate, and write the date beside it in the Spec. On Azure, the Azure Well-Architected Framework (five pillars, a living document with no edition) stands where the pack cites the AWS one.

## Pick the placement

| The workload | Start with | Why not the others |
| --- | --- | --- |
| Spiky or low traffic, short requests, idle most of the day | functions | a container or VM bills while idle |
| Latency-sensitive and global, little CPU per request, data that tolerates edge caching | edge functions | a regional function adds the round trip |
| Steady traffic above the break-even below, long requests, or many open connections | containers (scale to zero where the platform allows) | functions cost more per request at a steady load |
| Special hardware, a licensed or stateful server, or a steady load reserved for 1 to 3 years | VMs, with a Savings Plan or committed use | the managed options do not offer it, or cost more at a steady load |

Stop and write a design question when a request does one of these:

- It can run past the platform's time limit.
- It holds a connection the platform cannot keep.
- It needs read-after-write consistency from an eventually consistent store.

## Provider map

| Need | AWS | Google Cloud | Cloudflare | Azure |
| --- | --- | --- | --- | --- |
| Functions | Lambda | Cloud Run functions | Workers | Azure Functions |
| Containers | ECS or EKS on Fargate | Cloud Run | Containers | Container Apps |
| VMs | EC2 | Compute Engine | — | Virtual Machines |
| Database connection pool | RDS Proxy | PgBouncer | Hyperdrive | PgBouncer |
| Key-value at the edge | — | — | Workers KV | — |

## Limits that decide a placement

- **Lambda:** a timeout of at most 900 seconds. 128 to 10,240 MB of memory, with CPU in proportion (one vCPU at 1,769 MB). 1,000 concurrent executions per Region by default, raisable. SnapStart supports Java 11 and later, Python 3.12 and later, and .NET 8 and later. It does not support provisioned concurrency, Amazon EFS, or ephemeral storage above 512 MB.
- **Cloud Run:** the request timeout defaults to 5 minutes and can be raised to 60.
- **Workers (Paid):** 5 minutes of CPU time per invocation at most (30 seconds by default), 128 MB of memory, six simultaneous outgoing connections per request.
- **D1:** 10 GB per database; it is built to scale out across many small databases (per user or per tenant).
- **Workers KV:** eventually consistent; a change can take 60 seconds or more to be visible elsewhere, so never read your own write from it.
- **Hyperdrive:** pools connections to the database in the regions nearest it, so short-lived Workers do not open one each.

## List prices

Read the price on the provider's page; never copy it from here. Each link was checked on 2026-10-07.

| Service | Pricing page |
| --- | --- |
| AWS Lambda | <https://aws.amazon.com/lambda/pricing/> |
| AWS Fargate | <https://aws.amazon.com/fargate/pricing/> |
| AWS Savings Plans | <https://aws.amazon.com/savingsplans/compute-pricing/> |
| Google Cloud Run (request-based and instance-based billing) | <https://cloud.google.com/run/pricing> |
| Cloudflare Workers | <https://developers.cloudflare.com/workers/platform/pricing/> |
| Cloudflare Containers | <https://developers.cloudflare.com/containers/platform/pricing/> |
| Azure | <https://azure.microsoft.com/en-us/pricing/calculator/> |

## Break-even worksheet

1. Cost per request on functions: `price per request + duration (s) × memory (GB) × price per GB-second`.
2. Cost a month of the smallest always-on container: `hours (730) × (vCPU × vCPU-hour price + GB × GB-hour price) × instances`, plus what the functions do not need (a load balancer).
3. Break-even requests a month: step 2 ÷ step 1. Below it, functions; above it, containers; far above it and steady, a Savings Plan.

Use list prices before free tiers, for the region the service runs in. A load balancer in step 2 moves the break-even higher. Cloud Run bills active instance time, not each request. With concurrency above one, requests share that time, so divide the compute part by the concurrency you measured. On Workers, add the CPU milliseconds of each request to the price per request.

Write the result in the Spec: the placement, the estimate at today's load and at 10x, and the line of this worksheet that decided it.
