# Feature Specification: Photo albums

**Feature Branch**: `001-photo-albums`
**Created**: 2026-09-20
**Status**: Draft
**Input**: User description: "Let people group their photos into albums they can rename and reorder, because a flat camera roll is hard to browse."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create an album (Priority: P1)

A person groups photos into a named album.

**Why this priority**: Without albums nothing else in this feature works.

**Independent Test**: Create an album with two photos and see it listed.

**Acceptance Scenarios**:

1. **Given** a library with three photos, **When** the user creates "Trip" with two of them, **Then** "Trip" is listed with 2 photos
2. **Given** an album "Trip", **When** the user renames it to "Rome", **Then** only "Rome" is listed

---

### User Story 2 - Reorder albums (Priority: P2)

**Acceptance Scenarios**:

1. **Given** albums "A" then "B", **When** the user drags "B" above "A", **Then** the list shows "B" then "A"

### Edge Cases

- What happens when an album is empty?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST let users create an album from selected photos
- **FR-002**: System MUST keep the album order per user

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user creates an album in under 30 seconds
