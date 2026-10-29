# Design

## Context

The app has one hard-coded palette.

## Goals / Non-Goals

**Goals:** a dark palette. **Non-Goals:** per-page themes.

## Decisions

CSS custom properties hold the palette; a data-theme attribute on the root switches it.

## Risks / Trade-offs

Third-party widgets keep their own colors.
