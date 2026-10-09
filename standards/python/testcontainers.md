+++
id = "python/testcontainers"
type = "opinionated"
fills = ["test-design:integration-test-services"]
default = true
implements = "test-design:Real throwaway dependencies"
roles = ["developer", "tester", "reviewer"]
when_changed = ["tests/**", "**/conftest.py", "pyproject.toml"]
why = "testcontainers-python starts the real database and services from pytest, one throwaway container each, and gives each service's address to the test."
reviewed = "2026-10-09"
owner = "@thaithienvanid"
maturity = "established"
tool = { name = "testcontainers-python", registry = "pypi", package = "testcontainers" }
version_policy = "current_stable"
checked_version = "4.15.0"
checked = "2026-10-09"
checked_by = "agent:claude-code/claude-opus-5-5"
pin = "4.15.0"
source = "https://testcontainers-python.readthedocs.io/en/latest/"
evidence = "testcontainers-python facilitates the use of Docker containers for functional and integration testing."
alternatives = ["Docker Compose started by the test run", "the provider's local emulator"]
status = "active"
enforced_by = [
  { name = "integration", command = ["uv", "run", "pytest", "-m", "integration"] },
]
+++

# Testcontainers starts the Python integration-test services

It answers the integration-test-services choice of `aidd-team:test-design`. testcontainers-python is under the Apache License 2.0.

## What the team does

- Add `testcontainers` at the version in `pin` as a dev dependency, with an extra for each service, such as `testcontainers[postgres]`. Only the core package follows SemVer, and a community module can break in a minor release, so read the changelog before you move.
- Start each container in a pytest fixture with a `with` block, so the container stops when the fixture ends.
- Name each image with its tag and its digest, on the same major release as production.
- Read the address from the container, such as `get_connection_url()`, never from a fixed host or port.
- Mark each such test `@pytest.mark.integration`, register the marker, and add `-m 'not integration'` to `addopts`, so the unit run needs no Docker.

## What the gate runs

One `[[tests]]` entry runs `pytest -m integration`, which overrides the filter in `addopts`. A failing test, a container that does not start, or no marked test at all fails the change.
