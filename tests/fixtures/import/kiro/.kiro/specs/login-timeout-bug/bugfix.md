# Bugfix Document

## Current Behavior (Defect)

WHEN a session is idle for exactly 30 minutes THEN the system signs the user out while they type

## Expected Behavior (Correct)

WHEN a session is idle for 30 minutes and the user is typing THEN the system SHALL keep the session

## Unchanged Behavior (Regression Prevention)

WHEN a session is idle for 30 minutes with no input THEN the system SHALL CONTINUE TO sign the user out
