# Developer Guide

## Rootfile Operators

New runtime operators should declare their lawful-collapse position with
`OperatorMeta`:

```python
from core.meta import OperatorMeta, declare_operator

META = OperatorMeta(
    tier="rootfile",
    layer="trading.risk",
    operator_type="risk_projector",
    canonical_law="H8",
)

@declare_operator(META)
class RiskProjector:
    ...
```

Existing dict-style `META` declarations remain valid. The compatibility layer in
`core/meta.py` normalizes both forms.

## Invariant-First Design

Add new behavior as a refusal-first operator:

- Define which canonical law owns it.
- State the invariant it enforces.
- Emit evidence for refusal and success paths.
- Keep side effects behind scheduler authority and execution-token checks.

## Validation

Run rootfile validation before publishing architecture changes:

```powershell
python -m tools.validate_rootfile --repo-root .
python -m pytest tests/rootfile -q
```

`tools/validate_rootfile.py` verifies declared operator metadata against
`core/rootfile_manifest.py`. Use `--strict-missing` only for focused cleanup
branches because much of the older code is still metadata-optional.

## Adding A Hamiltonian Adapter

Prefer an adapter over a disruptive directory move. Put broker-neutral law APIs
under `core/orchestration` or `trading/kernel`, keep existing imports working,
and wire the adapter into the pipeline behind an environment flag if behavior is
still being calibrated.
