# Contributing

## Rootfile Runtime Checks

Before opening a PR that touches runtime architecture, run:

```powershell
python -m tools.validate_rootfile --repo-root .
python -m pytest tests/rootfile -q
```

The GitHub workflow also runs rootfile manifest validation. New operators should
declare `OperatorMeta` with a valid `canonical_law` from H1 through H13.

## Safety Defaults

Validation and test work must be offline and non-mutating by default. Broker
network checks, state clearing, canaries, and real-money execution require
explicit opt-in commands and review.

## Runtime Artifacts

Do not commit `.env`, raw `logs/`, raw `data/`, or broker canary artifacts.
