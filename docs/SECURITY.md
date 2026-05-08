# Security Notes

## Secrets

Never commit broker tokens, private keys, `.env`, runtime logs, or generated data
artifacts. Deriv tokens pasted into chat or logs should be treated as compromised
and rotated or revoked before future canary work.

## External Anchoring

External evidence anchoring is disabled by default. If enabled, credentials must
come from environment variables or a secrets manager, not source files. Missing
anchor configuration records `anchor_status=failed` and must not block local
evidence-chain append.

## QPT Ledger

QPT minting is disabled by default with `ENABLE_QPT=0`. The local QPT ledger is a
post-reconciliation artifact and should not contain secrets. It is not live-trade
approval and must not relax execution-token, demo-account, or risk boundaries.

## Live Trading Gate

Real-money execution remains locked until the full forward-proof, falsification,
risk, evidence, and operational safety gates are satisfied and reviewed.
