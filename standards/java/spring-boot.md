+++
id = "java/spring-boot"
type = "opinionated"
fills = ["apis-and-services:api-framework"]
default = true
implements = "apis-and-services:Schema conformance"
roles = ["architect", "developer", "reviewer"]
when_changed = ["src/main/**", "**/*.gradle.kts", "gradle/libs.versions.toml"]
why = "Spring Boot is the JVM's common framework for HTTP services, with production defaults for configuration, health, metrics, and security, and a dependency set that is tested together."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "established"
tool = { name = "spring-boot", registry = "maven", package = "org.springframework.boot:spring-boot" }
version_policy = "current_stable"
checked_version = "4.1.1"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
pin = "4.1.1"
source = "https://docs.spring.io/spring-boot/system-requirements.html"
evidence = "Spring Boot 4.1.1 requires at least Java 17 and is compatible with versions up to and including Java 26."
alternatives = ["Quarkus", "Micronaut", "Helidon"]
status = "active"
enforced_by = [
  { name = "contract", command = ["./gradlew", "--no-daemon", "test", "--tests", "*OpenApiContractTest"] },
]
+++

# Spring Boot serves the Java API

It answers the api-framework choice of `aidd-team:apis-and-services`.

## What the team does

- Apply the `org.springframework.boot` plugin at the version in `pin`, and let its dependency management set the Spring versions.
- Keep the OpenAPI document as the contract. Write the controllers to it, and validate each request body with Bean Validation (`@Valid`).
- Turn on Actuator's health and metrics endpoints, and expose only those the platform reads.
- Bind configuration with `@ConfigurationProperties` records, read from the environment.
- Use the Spring Boot generation the release calendar still supports, and upgrade one minor at a time.

## What the gate runs

One `[[tests]]` entry runs `OpenApiContractTest`: it starts the service with `@SpringBootTest` on a random port, calls each operation of the committed OpenAPI document, and validates each request and response against it. A response the contract does not allow fails the change.
