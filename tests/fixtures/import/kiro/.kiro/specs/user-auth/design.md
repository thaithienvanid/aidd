# Design Document

## Overview

A session endpoint checks the password hash and counts failures per account in the existing cache.

## Architecture

Unchanged apart from the new endpoint.

## Testing Strategy

Unit tests for the counter; an integration test for the endpoint.
