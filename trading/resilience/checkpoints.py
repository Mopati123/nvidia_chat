"""Hash-verified scheduler and risk recovery checkpoints."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict


CHECKPOINT_SCHEMA_VERSION = "t3a.scheduler_checkpoint.v1"


def _json_default(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "__dict__"):
        return vars(value)
    return str(value)


def stable_payload_hash(payload: Dict[str, Any]) -> str:
    """Return a deterministic hash for checkpoint payload validation."""
    import hashlib

    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass
class Checkpoint:
    """Tamper-evident state checkpoint."""

    component: str
    stage: str
    kind: str
    timestamp: float
    payload: Dict[str, Any]
    state_hash: str
    schema_version: str = CHECKPOINT_SCHEMA_VERSION
    evidence_hash: str = ""

    @classmethod
    def create(
        cls,
        *,
        component: str,
        stage: str,
        kind: str,
        payload: Dict[str, Any],
        evidence_hash: str = "",
    ) -> "Checkpoint":
        return cls(
            component=component,
            stage=stage,
            kind=kind,
            timestamp=time.time(),
            payload=payload,
            state_hash=stable_payload_hash(payload),
            evidence_hash=evidence_hash,
        )

    def validate(self) -> bool:
        """Return True when the payload still matches its stored hash."""
        return self.state_hash == stable_payload_hash(self.payload)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def persist_checkpoint(checkpoint_dir: str | Path, checkpoint: Checkpoint) -> Path:
    """Atomically persist a checkpoint JSON file and return its path."""
    if not checkpoint.validate():
        raise ValueError("checkpoint payload hash validation failed")

    directory = Path(checkpoint_dir)
    directory.mkdir(parents=True, exist_ok=True)
    safe_stage = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in checkpoint.stage)
    safe_kind = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in checkpoint.kind)
    filename = f"{checkpoint.component}_{safe_stage}_{safe_kind}_{int(checkpoint.timestamp * 1000)}.json"
    path = directory / filename
    tmp_path = path.with_suffix(path.suffix + ".tmp")

    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(checkpoint.to_dict(), handle, sort_keys=True, separators=(",", ":"), default=_json_default)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)
    return path


def load_checkpoint(path: str | Path) -> Checkpoint:
    """Load a checkpoint from disk without mutating it."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return Checkpoint(
        component=str(data["component"]),
        stage=str(data["stage"]),
        kind=str(data["kind"]),
        timestamp=float(data["timestamp"]),
        payload=dict(data["payload"]),
        state_hash=str(data["state_hash"]),
        schema_version=str(data.get("schema_version") or CHECKPOINT_SCHEMA_VERSION),
        evidence_hash=str(data.get("evidence_hash") or ""),
    )
