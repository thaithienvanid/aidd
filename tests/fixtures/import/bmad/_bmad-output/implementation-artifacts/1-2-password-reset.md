# Story 1.2: Password reset by email

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a customer who forgot my password,
I want to get a reset link by email,
so that I can sign in again without calling support.

## Acceptance Criteria

1. Given a registered email, when the customer asks for a reset, then a link valid for one hour is emailed
2. Given an unknown email, when the customer asks for a reset, then the page says the same as for a known one

## Tasks / Subtasks

- [ ] Task 1 (AC: #1)
  - [ ] Subtask 1.1 Token issue and check in `app/auth/reset_tokens.py`
- [ ] Task 2 (AC: #2)
  - [ ] Subtask 2.1 Same response in `app/views/reset.py`
  - [ ] Subtask 2.2 Tests in `app/tests/test_reset.py`

## Dev Notes

- Tokens follow the signing helper in `app/auth/signing.py`

### Project Structure Notes

- Views live in app/views/

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#Auth]

## Dev Agent Record

### Agent Model Used

### File List
