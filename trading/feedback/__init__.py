"""Feedback utilities for demo trading and ML settlement."""

from .demo_settlement import (
    DemoTrade,
    SettlementRecord,
    SettlementRunReport,
    classify_close_reason,
    load_demo_trades,
    settle_demo_trades,
    settle_trade,
)
from .deriv_settlement import (
    DerivContractTrade,
    DerivSettlementRecord,
    DerivSettlementRunReport,
    load_deriv_contract_trades,
    settle_deriv_contract,
    settle_deriv_contracts,
)
from .falsification import (
    FalsificationScore,
    append_falsification_evidence,
    score_decision,
)

__all__ = [
    "DerivContractTrade",
    "DerivSettlementRecord",
    "DerivSettlementRunReport",
    "DemoTrade",
    "FalsificationScore",
    "SettlementRecord",
    "SettlementRunReport",
    "append_falsification_evidence",
    "classify_close_reason",
    "load_deriv_contract_trades",
    "load_demo_trades",
    "score_decision",
    "settle_demo_trades",
    "settle_deriv_contract",
    "settle_deriv_contracts",
    "settle_trade",
]
