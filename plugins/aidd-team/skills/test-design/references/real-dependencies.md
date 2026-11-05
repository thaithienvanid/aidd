# Real throwaway dependencies

Load this when an integration test needs a database, a message broker, a cache, or another service the repository runs itself.

## Real at the integration level, mocked only at the edge

- A dependency you run (PostgreSQL, MySQL, Redis, Kafka, RabbitMQ, an S3-compatible store) is real in an integration test. The query planner, the constraints, the transaction isolation, and the wire protocol are what break in production. A mock has none of them.
- Mock only what you do not own or cannot run in CI: a payment provider, an email gateway, a clock, the network beyond your boundary. Keep each mock honest with a contract test or a recorded fixture.
- Unit tests stay in memory and fast. The real dependency belongs at the integration level, not in every test.
- The tech spec's Test strategy says what is real and what is mocked, one line per dependency.

## Throwaway containers

The `integration-test-services` choice decides how a test starts its dependencies. Its default is Testcontainers, an open source library that starts throwaway instances of anything that runs in a container, from inside the test code. It has libraries for Java, Go, .NET, Node.js, and Python, among others, so the same practice holds across stacks.

- **One container per test run.** Start it once per run, and stop it when the run ends. Use a session- or module-scoped fixture in pytest, a static container in JUnit, a global setup in Jest or Vitest, or `TestMain` in Go. Two runs, two developers, or two CI jobs never share one.
- **Pin the image** to the version production runs (`postgres:16-alpine`, never `latest`), so the test fails the way production would.
- **Seeded data.** The tests create the schema (the repository's own migrations) and the rows they need. A test never depends on data another test left. Each test cleans up, or runs in a transaction it rolls back.
- **No shared database.** When the container cannot start (no Docker in the environment), the run fails and says why. It never falls back to a developer's local database, a shared staging one, or another run's schema.
- **Configuration from the container.** Read the host, the mapped port, and the credentials from the running container, and pass them to the code under test. Never hard-code a port.
- **Clean up.** Stop the container in a finalizer or teardown, even when a test fails. Some language libraries also remove leftovers automatically, but do not rely on it.

A pytest sketch, with the Testcontainers library for Python:

```python
import pytest
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def database_url():
    with PostgresContainer("postgres:16-alpine") as pg:  # one container per test run, stopped on exit
        url = pg.get_connection_url()
        migrate(url)  # the repository's own migrations
        yield url


@pytest.fixture
def db(database_url):
    conn = connect(database_url)
    tx = conn.begin()
    seed(conn)  # the rows this test needs, and nothing else
    yield conn
    tx.rollback()  # no test sees another's data
```

Put the test configuration (the fixture file, the image tag) in `tests.files`, so Spec approval freezes it with the tests.
