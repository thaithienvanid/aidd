+++
id = "java/spring-data-jpa"
type = "opinionated"
fills = ["schema-migration:orm"]
default = true
implements = "schema-migration:Model drift check"
roles = ["developer", "data-engineer", "reviewer"]
when_changed = ["src/main/**", "src/integrationTest/**", "**/*.gradle.kts", "gradle/libs.versions.toml"]
why = "Spring Data JPA gives Spring Boot services repositories over JPA, with Hibernate as the provider, and Hibernate can check every entity against the migrated schema at startup."
reviewed = "2026-10-09"
owner = "@thaithienvanid"
maturity = "established"
tool = { name = "spring-data-jpa", registry = "maven", package = "org.springframework.data:spring-data-jpa" }
version_policy = "current_stable"
checked_version = "4.1.1"
checked = "2026-10-09"
checked_by = "agent:claude-code/claude-opus-5-5"
pin = "4.1.1"
source = "https://repo1.maven.org/maven2/org/springframework/boot/spring-boot-dependencies/4.1.1/spring-boot-dependencies-4.1.1.pom"
evidence = "<spring-data-bom.version>2026.0.1</spring-data-bom.version>"
alternatives = ["Spring Data JDBC", "jOOQ", "MyBatis"]
status = "active"
enforced_by = [
  { name = "schema", command = ["./gradlew", "--no-daemon", "integrationTest", "--tests", "*SchemaValidationTest"] },
]
+++

# Spring Data JPA maps the Java code to the database

It answers the orm choice of `aidd-team:schema-migration`. Spring Data JPA and Hibernate, the JPA provider that Spring Boot runs, are both under the Apache License 2.0.

## Which version

Spring Boot 4.1.1 manages the Spring Data release train that brings Spring Data JPA at `pin`. Add `spring-boot-starter-data-jpa`, and never override that version. Move with Spring Boot.

## What the team does

- Map each entity with JPA annotations, and declare one repository interface for each entity that the code loads and saves.
- Let the migration tool own the schema. Set `spring.jpa.hibernate.ddl-auto=validate`, so Hibernate checks the tables and never changes them.
- Write each query as a derived query method, or as `@Query` with named parameters. Never build JPQL or SQL from input.
- Load relations on purpose, with a fetch join or `@EntityGraph`.
- Keep one `SchemaValidationTest`: a `@SpringBootTest` on a Testcontainers database. The migrations run first, and then Hibernate validates each entity against the tables, so a mismatch stops the start.

## What the gate runs

One `[[tests]]` entry runs `SchemaValidationTest`. An entity that no longer matches the migrated schema fails the change.
