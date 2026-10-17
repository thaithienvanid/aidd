# Requirements Document

## Introduction

Customers cannot sign in with their email today; support resets accounts by hand. We want email and password sign-in with a lockout after repeated failures.

## Requirements

### Requirement 1

**User Story:** As a customer, I want to sign in with my email and password, so that I can reach my orders.

#### Acceptance Criteria

1. WHEN a customer submits a registered email and the right password THEN the system SHALL start a session
2. IF the password is wrong THEN the system SHALL show "Email or password is wrong" without saying which

### Requirement 2

WHEN a customer fails to sign in five times within ten minutes
THE SYSTEM SHALL lock the account for fifteen minutes
