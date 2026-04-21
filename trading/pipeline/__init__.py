"""
pipeline package - End-to-end trading pipeline orchestration.

Implements the 20-stage canonical transformation pipeline:
Raw Data → State Construction → Path Generation → Constraint Filtering
→ Action Evaluation → Interference Selection → Proposal → Admissibility
→ Entropy Gate → Scheduler → Execution → Reconciliation → Evidence → Learning
"""

from .orchestrator import PipelineOrchestrator, PipelineStage

__all__ = [
    'PipelineOrchestrator',
    'PipelineStage',
]
