---
id: java/flyway-migrations
type: opinionated
fills: [schema-migration:migration-tool]
default: true
implements: schema-migration:Migration up and down
roles: [developer, data-engineer, reviewer]
when_changed: ["src/main/resources/db/**", "src/integrationTest/**", gradle/libs.versions.toml]
why: "Flyway applies versioned SQL scripts in order and checks their checksums; with Spring Boot 4, spring-boot-starter-flyway runs it at startup, plus flyway-database-postgresql for Postgres."
reviewed: "2026-10-16"
maturity: established
tool:
  name: flyway
  registry: maven
  package: org.flywaydb:flyway-core
version_policy: pinned
checked_version: "13.9.0"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
pin: "12.4.0"
source: https://repo1.maven.org/maven2/org/springframework/boot/spring-boot-dependencies/4.1.1/spring-boot-dependencies-4.1.1.pom
evidence: "<flyway.version>12.4.0</flyway.version>"
alternatives: [Liquibase]
status: active
enforced_by:
  - name: migrate
    command: ["./gradlew", --no-daemon, integrationTest, --tests, "*MigrationTest"]
---

# Flyway writes and applies the Java schema migrations

It answers the migration-tool choice of `aidd-team:schema-migration`.

## Which version

Spring Boot's dependency management sets Flyway's version. `pin` is the one Spring Boot 4.1.1 manages, and `checked_version` is the newest Flyway release. Never override Spring Boot's version, even when a newer Flyway major is out. Move with Spring Boot.

## What the team does

- Add `spring-boot-starter-flyway`, and `flyway-database-postgresql` for Postgres.
- Write each change as `V<version>__<description>.sql` under `db/migration`. Never edit a script once it has run anywhere.
- Keep `validateOnMigrate` on and `outOfOrder` off in production.
- Undo migrations are a Flyway Teams feature. Keep each down script as `db/undo/U<version>__<description>.sql`, outside Flyway's locations.
- Keep one `MigrationTest` on a Testcontainers database: migrate to the head, run the newest undo script over JDBC, delete that version's row from `flyway_schema_history`, compare the schema with the one the previous version left, then migrate again.

## What the gate runs

One `tests` entry runs `MigrationTest`. A script that fails up, down, or its checksum fails the change.
