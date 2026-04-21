"""
TAEP - Tachyonic Algorithmic Encryption Protocol

A governed cryptographic state-transition system:
- Geometric substrate (H_geo)
- Three-body chaos engine (H_3B) 
- Statistical adaptation (H_stat)
- Game-theoretic modeling (H_game)
- Quantum layer (H_q)

With:
- Constraint enforcement (admissibility)
- Scheduler authority (collapse governance)
- Audit-first execution (evidence emission)
"""

from .core.state import TAEPState, ExecutionToken
from .core.master_equation import evolve_master_equation
from .scheduler.scheduler import TAEPScheduler
from .audit.evidence_writer import TAEPEvidence, EvidenceWriter

__all__ = [
    'TAEPState',
    'ExecutionToken',
    'evolve_master_equation',
    'TAEPScheduler',
    'TAEPEvidence',
    'EvidenceWriter',
]
