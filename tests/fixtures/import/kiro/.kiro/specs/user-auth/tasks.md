# Implementation Plan

- [ ] 1. Add the sign-in endpoint
  - Create `src/auth/session.py` with the password check
  - Register the route in `src/api/routes.py`
  - _Requirements: 1.1, 1.2_

- [ ] 2. Lock accounts after repeated failures
  - [ ] 2.1 Count failures in `src/auth/lockout.py`
  - [ ] 2.2 Write unit tests in `tests/auth/test_lockout.py`
  - _Requirements: 2_
