# Implementation Plan: Photo albums

**Branch**: `001-photo-albums` | **Date**: 2026-09-21 | **Spec**: [spec.md](spec.md)

## Summary

Albums are a new table joined to photos, served by two endpoints and shown in the library sidebar.

## Technical Context

**Language/Version**: Python 3.12
**Testing**: pytest

## Project Structure

```text
src/
├── models/
└── services/
```
