# First MT5 Demo Trade Anchor - 2026-05-04

## Summary

This report anchors the first successful MT5 demo forward-test trade for the
rootfile trading pipeline. The trade was routed through the live-demo MT5 path,
authorized by the scheduler token flow, executed on the Welltrade demo account,
closed by take profit, and settled from MT5 history into the offline ML feedback
artifacts.

Raw runtime outputs under `logs/` and `data/` remain local runtime artifacts and
are intentionally ignored by Git. This report records the durable identifiers,
hashes, and settlement result so the milestone is preserved in GitHub history.

## Trade Record

| Field | Value |
| --- | --- |
| Ticket | `353158067` |
| Broker | `MT5` |
| Account mode | Demo |
| Symbol | `EURUSD_r` |
| Direction | `BUY` |
| Size | `0.01` lot |
| Broker fill | `1.16970` |
| CSV entry | `1.16973` |
| Stop loss | `1.16873` |
| Take profit | `1.17173` |
| Close reason | `tp` |
| Realized net PnL | `+1.99` |
| PPO feedback status | `missing_pending_state` |

The PPO status is expected for this specific ticket because it was opened before
the live-demo pending-state persistence fix. Future live-demo trades should
persist PPO pending state at entry and feed realized closed-trade PnL to PPO
during settlement.

## Evidence Chain Anchors

The repo's current blockchain-style anchor is a local durable hash chain
implemented in `tachyonic_chain/audit_log.py`. Each evidence record includes
`previous_hash`, the canonical JSON payload, and `record_hash`.

| Evidence event | Execution ID | Record hash |
| --- | --- | --- |
| Broker execution | `mt5_353158067` | `8fec8f03342b16dd75acb64e16c680bcc7e1bb560bf0a1f4a3808e963f358f17` |
| MT5 settlement | `settled_mt5_353158067` | `4c42e00f9b93d3e1712048f1ca6d4e7b4b664fd78a3485e60efc6861be28097c` |

The settlement record links to the existing evidence chain through:

```text
previous_hash=ad18e6b39674e75b97df0a0ed78e83909a00981361edf176f295e3f546968c8e
record_hash=4c42e00f9b93d3e1712048f1ca6d4e7b4b664fd78a3485e60efc6861be28097c
```

Chain validation after settlement reported:

```text
evidence_chain_valid=true
```

## ML Feedback Outcome

The closed trade was settled from MT5 history using the full position lifecycle:
opening deal plus closing deal, including profit, swap, and commissions. The
settlement appended a closed-trade evidence record and rebuilt the offline
refusal/risk learning artifacts.

| Artifact | Result |
| --- | --- |
| Settlement ledger | local `logs/demo_trade_settlements.jsonl` |
| Evidence log | local `logs/execution_evidence.jsonl` |
| Refusal/risk dataset | rebuilt with `133` rows |
| Refusal/risk model | retrained with `22` features |
| Runtime integration | offline only |

## GitHub Anchor

Committing this report and the supporting code creates the public GitHub anchor
for the milestone. The local evidence hash chain proves the execution and
settlement sequence; the Git commit proves the code and milestone report state
that was published for review.

This is not a public-chain transaction. Public blockchain notarization can be
added later as a separate feature if required.
