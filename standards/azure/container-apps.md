---
id: azure/container-apps
type: opinionated
fills: [cloud-and-infrastructure:serverless-compute]
default: true
implements: cloud-and-infrastructure:Provider map
roles: [architect, developer, sre, reviewer]
when_changed: ["**/*.tf", "**/*.tofu", Dockerfile]
why: "Azure Container Apps runs an ASP.NET Core service, or any other container, on a consumption plan that scales to zero, so an API that waits for requests costs nothing while no replica runs."
reviewed: "2026-10-22"
maturity: established
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: [Azure Functions Flex Consumption, Azure App Service, Azure Kubernetes Service]
status: active
source: https://learn.microsoft.com/en-us/azure/container-apps/billing
evidence: When a revision is scaled to zero replicas, no resource consumption charges are incurred.
---

# Azure Container Apps runs the containers

It answers the serverless-compute choice of `aidd-team:cloud-and-infrastructure` on Azure.

## What Container Apps supports

As read on the `checked` day: an app runs only a Linux x86-64 (`linux/amd64`) image. With no scale rule of its own, an app scales from 0 to 10 replicas on HTTP traffic. A revision can have at most 1,000. A replica kept warm by a minimum above zero is billed at an idle rate.

## What the team does

- Run the apps in an environment on the Consumption workload profile, and build each image for `linux/amd64`.
- Set `min_replicas` to 0 outside production. Keep one warm replica in production only when the Spec names the latency that needs it.
- Set `max_replicas` on each app, at the most its database and its budget can take, never left at the default.
- Add an HTTP scale rule with the concurrency a load test measured.
- Run batch work as a Container Apps job, with a replica timeout and a retry limit.
- Define the environment, the apps, and their Log Analytics workspace in OpenTofu (`iac/opentofu`), with the `azurerm` provider pinned in `required_providers`. The provider is under MPL-2.0.
- Pull images with a managed identity, never with a registry password.
- Run event-driven functions on Azure Functions Flex Consumption, Microsoft's recommended serverless plan for Functions, with a maximum instance count.

## What the gate runs

Nothing of its own. Container Apps caps each revision at its maximum replica count, which is 10 unless the IaC sets another.
