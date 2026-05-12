# Project Analysis: Rootfile Architecture and Hamiltonians

## Project Structure
- .github/: 3 analyzed files
- apps/: 9 analyzed files
- backend_api/: 3 analyzed files
- config/: 1 analyzed files
- core/: 35 analyzed files
- data_core/: 6 analyzed files
- docs/: 25 analyzed files
- infra/: 1 analyzed files
- registry/: 4 analyzed files
- root/: 13 analyzed files
- scripts/: 26 analyzed files
- tachyonic_chain/: 3 analyzed files
- taep/: 19 analyzed files
- tests/: 28 analyzed files
- tools/: 6 analyzed files
- trading/: 123 analyzed files
- validation/: 27 analyzed files

## Canonical Layers
- .github
- Application Interfaces
- Backend API
- Configuration
- Core Canonical Runtime
- Data Core
- Documentation
- Evidence Chain
- Infrastructure
- Operational Scripts
- Registry Metadata
- Repository Root
- TAEP Authority
- Tests
- Tools
- Trading Engine
- Validation

## Key Runtime Areas
- Authority and token validation: core/authority, taep, and trading/kernel.
- Orchestration and scheduler collapse: core/orchestration and trading/kernel.
- Simulation and market geometry: core/simulation and trading geometry/path-integral modules.
- Execution boundaries: core/execution, apps, broker adapters, and trading runtime code.
- Evidence and validation: tachyonic_chain, validation, tests, and rootfile suites.

## Refresh Metadata
- Commit: fa8f001645f56d802f6a0d80e40236ecba744d8c
- Timestamp: 2026-05-12T15:03:45.754Z
- Files analyzed: 332
