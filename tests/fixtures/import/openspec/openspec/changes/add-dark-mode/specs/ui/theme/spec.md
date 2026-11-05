# Spec Delta

## Purpose

The user's choice of theme.

## ADDED Requirements

### Requirement: Theme selection

The app SHALL let users switch between light and dark themes.

#### Scenario: Choosing dark

- **WHEN** the user selects the dark theme
- **THEN** every page renders with the dark palette

#### Scenario: Following the system

- **WHEN** the theme is "system" and the OS switches to dark
- **THEN** the app switches to dark without a reload

## REMOVED Requirements

### Requirement: Fixed palette

**Reason**: replaced by theme selection. **Migration**: none.
