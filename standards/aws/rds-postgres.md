---
id: aws/rds-postgres
type: opinionated
fills: [cloud-and-infrastructure:database]
default: false
implements: cloud-and-infrastructure:Database connection pool
roles: [architect, developer, sre, reviewer]
when_changed: ["**/*.tf", "**/*.tofu"]
why: "Amazon RDS for PostgreSQL runs PostgreSQL 18 with automated backups and point-in-time recovery on Graviton classes, so a relational workload on AWS gets a managed database with each cost driver in the IaC."
reviewed: "2026-10-22"
maturity: established
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: [Amazon Aurora PostgreSQL, Aurora Serverless v2, Amazon DynamoDB]
status: active
source: https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_WorkingWithAutomatedBackups.html
evidence: If necessary, you can recover your DB instance to any point in time during the backup retention period.
---

# Amazon RDS for PostgreSQL holds relational data on AWS

It answers the database choice of `aidd-team:cloud-and-infrastructure` on AWS, and applies `postgres/managed-postgres` to RDS. aidd's default on AWS, for key-value data, is `aws/dynamodb-on-demand`.

## What RDS supports

As read on the `checked` day: RDS runs PostgreSQL 18.6. A stopped instance starts again on its own after 7 days. A major version past its RDS end of standard support keeps running only under RDS Extended Support, at an extra charge.

## What the team does

- Set `engine_version` to the major, `auto_minor_version_upgrade = true`, and a maintenance window.
- Set `backup_retention_period` to 7 days or more, `deletion_protection = true`, and a final snapshot.
- Choose Multi-AZ in production only when the Spec's RTO needs a standby. Run a single instance elsewhere.
- Use a Graviton instance class, such as `db.t4g` or `db.m7g`, and gp3 storage.
- Set `max_allocated_storage` as the cap on storage autoscaling.
- Put RDS Proxy in front of Lambda functions or of many tasks, and set the timeouts on the application's role as `postgres/managed-postgres` describes.
- Stop non-production instances outside working hours on a schedule, which stops each one again after RDS restarts it.
- Set `engine_lifecycle_support = "open-source-rds-extended-support-disabled"` outside production, so RDS upgrades a forgotten major rather than charging for Extended Support.
- Turn on storage encryption and IAM database authentication.

## What the gate runs

Nothing of its own. The pack's Plan or dry-run check fails a plan that replaces the instance without the Spec naming it.
