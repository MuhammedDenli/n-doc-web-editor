# API contract

`openapi.json` in this directory is the single source of truth between
backend and frontend.

## Rules

1. Any API change lands first as a small, separate contract commit.
2. Backend and frontend implement the change afterwards.
3. Frontend types are generated from `openapi.json` (`openapi-typescript`),
   never written by hand.

## Endpoints

_None yet — defined in Phase 4._
