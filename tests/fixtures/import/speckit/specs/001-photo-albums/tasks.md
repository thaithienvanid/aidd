---
description: "Task list template for feature implementation"
---

# Tasks: Photo albums

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup (Shared Infrastructure)

- [ ] T001 Create project structure per implementation plan

## Phase 3: User Story 1 - Create an album (Priority: P1) 🎯 MVP

### Tests for User Story 1

- [ ] T010 [P] [US1] Contract test for POST /albums in tests/contract/test_albums.py

### Implementation for User Story 1

- [ ] T012 [P] [US1] Create Album model in src/models/album.py
- [ ] T014 [US1] Implement AlbumService in src/services/albums.py (depends on T012)

## Phase 4: User Story 2 - Reorder albums (Priority: P2)

- [ ] T020 [US2] Add the order column in src/models/album.py and the sort in src/services/albums.py

## Dependencies & Execution Order

- Phase 3 before Phase 4
