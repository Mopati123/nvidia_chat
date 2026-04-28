"""
pipeline package - End-to-end trading pipeline orchestration.

Implements the 20-stage canonical transformation pipeline:
Raw Data → State Construction → Path Generation → Constraint Filtering
→ Action Evaluation → Interference Selection → Proposal → Admissibility
→ Entropy Gate → Scheduler → Execution → Reconciliation → Evidence → Learning
"""

from .orchestrator import PipelineOrchestrator, PipelineStage

try:
    from ._rootfile_enforcement import install_pipeline_token_bridge

    install_pipeline_token_bridge()
except Exception:
    # Pipeline imports should not fail because optional enforcement shims failed.
    pass

__all__ = [
    'PipelineOrchestrator',
    'PipelineStage',
]
