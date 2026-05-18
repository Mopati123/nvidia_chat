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
- root/: 12 analyzed files
- scripts/: 26 analyzed files
- tachyonic_chain/: 3 analyzed files
- taep/: 19 analyzed files
- tests/: 29 analyzed files
- tools/: 6 analyzed files
- trading/: 117 analyzed files
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

## Rootfile H1-H13 Execution Map
- H1-H4 prepare typed market state, liquidity geometry, connection, and curvature diagnostics.
- H5-H7 generate candidate futures, compress behavior families, and score path action.
- H8-H9 refuse inadmissible proposals and require measured entropy/information gain before collapse.
- H10 gives scheduler authority sole permission to issue execution tokens.
- H11 allows broker execution only after execution-boundary token validation.
- H12 reconciles intended vs realized broker outcomes for settlement and learning.
- H13 records every refusal, authorization, execution, audit, and settlement into verifiable evidence.

## Key Runtime Areas
- Authority and token validation: core/authority, taep, and trading/kernel.
- Orchestration and scheduler collapse: core/orchestration and trading/kernel.
- Simulation and market geometry: core/simulation and trading geometry/path-integral modules.
- Execution boundaries: core/execution, apps, broker adapters, and trading runtime code.
- Evidence and validation: tachyonic_chain, validation, tests, and rootfile suites.

## Refresh Metadata
- Commit: c08fa30c99674c42e3b597bf0a0579eee6c60d68
- Timestamp: 2026-05-13T11:33:15.390Z
- Files analyzed: 326
