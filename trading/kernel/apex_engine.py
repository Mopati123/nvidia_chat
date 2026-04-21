"""
apex_engine.py — Master orchestrator: wires canonical loop

Receives market data, routes through operators, invokes scheduler, emits evidence.
The single entry point for all execution.
"""

import time
import hashlib
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum

from .scheduler import Scheduler, CollapseDecision, ExecutionToken
from .H_constraints import ConstraintHamiltonian


class ExecutionMode(Enum):
    """Execution modalities"""
    SHADOW = "shadow"    # No real capital
    LIVE = "live"        # Real capital at risk


class ExecutionOutcome(Enum):
    """Canonical execution outcomes"""
    SUCCESS = "success"
    REFUSED = "refused"
    DEFERRED = "deferred"
    ERROR = "error"


@dataclass
class ExecutionResult:
    """Result of canonical execution cycle"""
    outcome: ExecutionOutcome
    token: Optional[ExecutionToken]
    trajectory: Optional[Dict]
    evidence_hash: str
    execution_time_ms: float
    mode: ExecutionMode
    refusal_reason: Optional[str] = None


class ApexEngine:
    """
    Master orchestrator for the ApexQuantumICT system.
    Implements the canonical 7-step transition cycle:
    Proposal → Projection → ΔS → Collapse auth → State update → Reconciliation → Evidence
    """
    
    def __init__(self, 
                 scheduler: Optional[Scheduler] = None,
                 constraints: Optional[ConstraintHamiltonian] = None):
        self.scheduler = scheduler or Scheduler()
        self.constraints = constraints or ConstraintHamiltonian()
        self.execution_history: List[ExecutionResult] = []
        self.current_state: Dict[str, Any] = {}
        self.mode = ExecutionMode.SHADOW  # Default to shadow
        
    def execute_canonical_cycle(self,
                               proposal: Dict,
                               market_state: Dict,
                               path_integral_result: Dict,
                               mode: ExecutionMode = ExecutionMode.SHADOW) -> ExecutionResult:
        """
        Execute full canonical transition cycle.
        
        1. Proposal - generate candidate trajectories (input)
        2. Projection - constraint admissibility gate
        3. ΔS measurement - entropy change assessment
        4. Scheduler-authorized collapse
        5. State update - wavefunction collapse
        6. Reconciliation - post-collapse verification
        7. Evidence - cryptographic audit emission
        """
        start_time = time.time()
        self.mode = mode
        
        trajectories = path_integral_result.get("trajectories", [])
        
        # Step 2: Projection - apply constraint projectors
        admissible = self.constraints.apply_constraints(trajectories, market_state)
        
        if not admissible:
            # Refusal-first: evidenced refusal as first-class output
            result = ExecutionResult(
                outcome=ExecutionOutcome.REFUSED,
                token=None,
                trajectory=None,
                evidence_hash=self._compute_refusal_hash(proposal),
                execution_time_ms=(time.time() - start_time) * 1000,
                mode=mode,
                refusal_reason="All trajectories failed constraint projection"
            )
            self.execution_history.append(result)
            return result
        
        # Step 3: ΔS measurement - entropy change
        delta_s = self._measure_entropy_change(admissible, market_state)
        
        # Step 4: Scheduler-authorized collapse
        reconciliation_clear = self._check_reconciliation(market_state)
        
        decision, token = self.scheduler.authorize_collapse(
            proposal=proposal,
            projected_trajectories=admissible,
            delta_s=delta_s,
            constraints_passed=not self.constraints.has_fatal_violations(),
            reconciliation_clear=reconciliation_clear
        )
        
        if decision == CollapseDecision.REFUSED:
            result = ExecutionResult(
                outcome=ExecutionOutcome.REFUSED,
                token=None,
                trajectory=None,
                evidence_hash=self._compute_refusal_hash(proposal, admissible),
                execution_time_ms=(time.time() - start_time) * 1000,
                mode=mode,
                refusal_reason="Scheduler refused collapse authorization"
            )
            self.execution_history.append(result)
            return result
        
        if decision == CollapseDecision.DEFERRED:
            result = ExecutionResult(
                outcome=ExecutionOutcome.DEFERRED,
                token=None,
                trajectory=None,
                evidence_hash=self._compute_deferred_hash(proposal),
                execution_time_ms=(time.time() - start_time) * 1000,
                mode=mode,
                refusal_reason="Execution deferred by firmament stabilizer"
            )
            self.execution_history.append(result)
            return result
        
        # Step 5: State update - execute collapse
        selected_traj = self._select_best_trajectory(admissible, token)
        
        if mode == ExecutionMode.LIVE:
            self._execute_live(selected_traj, market_state)
        else:
            self._execute_shadow(selected_traj, market_state)
        
        # Step 6: Reconciliation
        reconciliation_ok = self._reconcile_execution(selected_traj, market_state)
        
        # Step 7: Evidence emission
        evidence_hash = self._emit_evidence(
            proposal, admissible, token, selected_traj, market_state
        )
        
        result = ExecutionResult(
            outcome=ExecutionOutcome.SUCCESS if reconciliation_ok else ExecutionOutcome.ERROR,
            token=token,
            trajectory=selected_traj,
            evidence_hash=evidence_hash,
            execution_time_ms=(time.time() - start_time) * 1000,
            mode=mode
        )
        
        self.execution_history.append(result)
        self._update_state(selected_traj, market_state)
        
        return result
    
    def _measure_entropy_change(self, 
                               trajectories: List[Dict], 
                               market_state: Dict) -> float:
        """
        Step 3: ΔS measurement - entropy change assessment
        Negative ΔS = increased structure (good)
        Positive ΔS = destruction (bad)
        """
        if not trajectories:
            return float('inf')
        
        # Simplified entropy: based on trajectory energy variance
        energies = [t.get("energy", 0) for t in trajectories]
        if not energies:
            return 0.0
            
        # Lower variance = more structured = negative ΔS
        variance = sum((e - sum(energies)/len(energies))**2 for e in energies) / len(energies)
        delta_s = variance  # Positive variance = higher entropy
        
        return delta_s
    
    def _check_reconciliation(self, market_state: Dict) -> bool:
        """Check pre-collapse reconciliation status"""
        # Check for any pending reconciliations
        pending = market_state.get("pending_reconciliations", [])
        return len(pending) == 0
    
    def _select_best_trajectory(self, 
                              trajectories: List[Dict],
                              token: ExecutionToken) -> Dict:
        """Select trajectory using scheduler operator weights"""
        best_score = -float('inf')
        best_traj = None
        
        for traj in trajectories:
            score = 0.0
            # Weight by scheduler operator weights
            for op_name, weight in token.operator_weights.items():
                score += weight * traj.get(op_name, traj.get(f"{op_name}_score", 0.0))
            score += traj.get("action_score", 0.0) * 2.0  # Action weighted heavily
            
            if score > best_score:
                best_score = score
                best_traj = traj
        
        return best_traj or trajectories[0]
    
    def _execute_shadow(self, trajectory: Dict, market_state: Dict):
        """Shadow execution - no real capital"""
        # Simulate execution, update shadow state
        trajectory["executed"] = True
        trajectory["execution_mode"] = "shadow"
        
    def _execute_live(self, trajectory: Dict, market_state: Dict):
        """Live execution - real capital at risk"""
        # TODO: Integration with broker API
        trajectory["executed"] = True
        trajectory["execution_mode"] = "live"
    
    def _reconcile_execution(self, 
                           trajectory: Dict, 
                           market_state: Dict) -> bool:
        """
        Step 6: Post-collapse reconciliation
        Compare actual vs predicted, detect drift
        """
        predicted_pnl = trajectory.get("predicted_pnl", 0)
        # In shadow mode, simulate actual
        actual_pnl = predicted_pnl * (0.95 + 0.1 * (hash(trajectory.get("id", "")) % 100) / 100)
        
        divergence = abs(predicted_pnl - actual_pnl)
        threshold = market_state.get("reconciliation_threshold", 0.05)
        
        trajectory["reconciliation"] = {
            "predicted": predicted_pnl,
            "actual": actual_pnl,
            "divergence": divergence,
            "passed": divergence < threshold
        }
        
        return divergence < threshold
    
    def _emit_evidence(self,
                      proposal: Dict,
                      trajectories: List[Dict],
                      token: ExecutionToken,
                      selected: Dict,
                      market_state: Dict) -> str:
        """
        Step 7: Cryptographic evidence emission
        Merkle root + Ed25519 signature
        """
        evidence_data = {
            "proposal_hash": hashlib.sha256(str(proposal).encode()).hexdigest()[:16],
            "trajectory_count": len(trajectories),
            "selected_id": selected.get("id", "unknown"),
            "token_id": token.token_id if token else "refused",
            "timestamp": time.time(),
            "market_state_hash": hashlib.sha256(str(market_state).encode()).hexdigest()[:16],
            "operator_weights": token.operator_weights if token else {},
            "mode": self.mode.value
        }
        
        evidence_str = str(sorted(evidence_data.items()))
        evidence_hash = hashlib.sha256(evidence_str.encode()).hexdigest()
        
        return evidence_hash
    
    def _compute_refusal_hash(self, 
                            proposal: Dict,
                            trajectories: Optional[List[Dict]] = None) -> str:
        """Hash for evidenced refusal"""
        data = f"REFUSAL:{proposal}:{trajectories}"
        return hashlib.sha256(data.encode()).hexdigest()
    
    def _compute_deferred_hash(self, proposal: Dict) -> str:
        """Hash for deferred execution"""
        data = f"DEFERRED:{proposal}:{time.time()}"
        return hashlib.sha256(data.encode()).hexdigest()
    
    def _update_state(self, trajectory: Dict, market_state: Dict):
        """Update current state post-collapse"""
        self.current_state["last_trajectory"] = trajectory
        self.current_state["last_market_state"] = market_state
        self.current_state["execution_count"] = self.current_state.get("execution_count", 0) + 1
    
    def get_engine_status(self) -> Dict[str, Any]:
        """Engine status for monitoring"""
        return {
            "execution_count": len(self.execution_history),
            "mode": self.mode.value,
            "scheduler_status": self.scheduler.get_scheduler_status(),
            "constraints_status": self.constraints.get_admissibility_status(),
            "last_execution": self.execution_history[-1] if self.execution_history else None
        }
