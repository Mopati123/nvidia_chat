"""Evidence bundle signature verification tests."""

from __future__ import annotations

from trading.evidence.evidence_chain import Ed25519Signer, EvidenceEmitter


def _emitter() -> EvidenceEmitter:
    signer = Ed25519Signer(private_key_pem=Ed25519Signer.generate_key_pem())
    return EvidenceEmitter(signer=signer)


def _bundle():
    emitter = _emitter()
    bundle = emitter.emit(
        execution_id="exec_bundle_1",
        inputs={"symbol": "EURUSD", "price": 1.1},
        operators_applied=["state", "geometry", "scheduler"],
        constraints_checked=["risk", "entropy"],
        scheduler_decision="AUTHORIZED",
        execution_result={"mode": "shadow", "ticket": "paper-1"},
        reconciliation_delta=0.0,
        system_state={"version": "test"},
    )
    return emitter, bundle


def test_evidence_bundle_emit_then_verify_succeeds():
    emitter, bundle = _bundle()

    assert emitter.verify_bundle(bundle.bundle_id) is True


def test_evidence_bundle_verify_rejects_tampered_merkle_root():
    emitter, bundle = _bundle()
    bundle.merkle_root = "0" * 64

    assert emitter.verify_bundle(bundle.bundle_id) is False


def test_evidence_bundle_verify_rejects_tampered_timestamp():
    emitter, bundle = _bundle()
    bundle.timestamp += 1.0

    assert emitter.verify_bundle(bundle.bundle_id) is False


def test_evidence_bundle_verify_rejects_signature_mismatch():
    emitter, bundle = _bundle()
    bundle.signature = "00" * 64

    assert emitter.verify_bundle(bundle.bundle_id) is False
