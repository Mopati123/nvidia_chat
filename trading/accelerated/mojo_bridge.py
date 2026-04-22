"""
mojo_bridge.py — Python bridge to Mojo engine

Enables calling Mojo from Python until direct interop is available.
"""

import mmap
import os
import struct
import subprocess
import json
import logging
import tempfile
from typing import Dict, List, Optional, Any
import numpy as np

logger = logging.getLogger(__name__)

MOJO_AVAILABLE = False
MOJO_BINARY_PATH = None

def check_mojo_available() -> bool:
    """Check if Mojo compiler and runtime are available"""
    global MOJO_AVAILABLE, MOJO_BINARY_PATH
    
    try:
        # Check if mojo command is available
        result = subprocess.run(
            ['mojo', '--version'],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            logger.info(f"✓ Mojo available: {result.stdout.strip()}")
            
            # Check for pre-built binary
            binary_path = os.path.join(
                os.path.dirname(__file__),
                'mojo', 'core', 'trajectory_engine'
            )
            
            if os.path.exists(binary_path):
                MOJO_BINARY_PATH = binary_path
                MOJO_AVAILABLE = True
                logger.info(f"✓ Mojo binary found: {binary_path}")
            else:
                logger.warning("⚠ Mojo binary not built. Run: mojo build trajectory_engine.mojo")
            
            return MOJO_AVAILABLE
    except FileNotFoundError:
        logger.debug("Mojo not installed")
    
    return False


_SHMEM_SIZE = 4 * 1024 * 1024   # 4 MB shared-memory window


class MojoEngineBridge:
    """
    Bridge to Mojo-accelerated engine.

    IPC strategy (T2-H):
        1. Try mmap-based IPC: single temp file, length-prefixed JSON, no extra
           file-open round-trip — binary called with --mmap <path>.
        2. Fall back to original two-file JSON IPC if mmap call fails or the
           binary does not support --mmap.

    Falls back to Cython or NumPy if Mojo is unavailable.
    """

    def __init__(self):
        self.available = check_mojo_available()
        self.binary_path = MOJO_BINARY_PATH

    # ------------------------------------------------------------------
    # T2-H: mmap IPC helper
    # ------------------------------------------------------------------

    def _call_mojo_mmap(self,
                        payload: Dict,
                        extra_args: Optional[List[str]] = None,
                        timeout: int = 10) -> Optional[Dict]:
        """
        Call the Mojo binary using mmap-backed IPC.

        Protocol (both sides of the file):
            Offset 0: uint32 LE   — length of JSON payload in bytes
            Offset 4: <len bytes> — UTF-8 JSON input (written by Python)

        After the subprocess returns the binary has overwritten the buffer:
            Offset 0: uint32 LE   — length of JSON output in bytes
            Offset 4: <len bytes> — UTF-8 JSON output

        Returns parsed output dict, or None on any failure.
        """
        args = extra_args or []
        with tempfile.NamedTemporaryFile(delete=False, suffix=".shm") as tf:
            shm_path = tf.name
            tf.write(b"\x00" * _SHMEM_SIZE)

        try:
            data = json.dumps(payload).encode("utf-8")
            if len(data) + 4 > _SHMEM_SIZE:
                logger.warning("Payload too large for mmap IPC; falling back")
                return None

            with open(shm_path, "r+b") as f:
                mm = mmap.mmap(f.fileno(), _SHMEM_SIZE)
                # Write input: 4-byte length prefix + JSON
                mm[:4] = struct.pack("<I", len(data))
                mm[4:4 + len(data)] = data
                mm.flush()

                result = subprocess.run(
                    [self.binary_path, "--mmap", shm_path] + args,
                    capture_output=True,
                    timeout=timeout,
                )

                if result.returncode != 0:
                    logger.debug("Mojo --mmap failed (rc=%d): %s",
                                 result.returncode, result.stderr[:200])
                    return None

                mm.seek(0)
                out_len = struct.unpack("<I", mm.read(4))[0]
                if out_len == 0 or out_len > _SHMEM_SIZE - 4:
                    return None
                out_bytes = mm.read(out_len)
                return json.loads(out_bytes.decode("utf-8"))
        except Exception as exc:
            logger.debug("mmap IPC error: %s", exc)
            return None
        finally:
            try:
                os.unlink(shm_path)
            except OSError:
                pass
    
    def generate_trajectories(
        self,
        initial_price: float,
        initial_velocity: float,
        potential_force: float,
        n_trajectories: int = 100,
        n_steps: int = 50,
        epsilon: float = 0.015
    ) -> Optional[Dict]:
        """
        Call Mojo engine to generate trajectories.
        
        Returns trajectory data or None if failed.
        """
        if not self.available:
            return None

        input_data = {
            'initial_price': initial_price,
            'initial_velocity': initial_velocity,
            'potential_force': potential_force,
            'n_trajectories': n_trajectories,
            'n_steps': n_steps,
            'epsilon': epsilon,
        }

        # T2-H: try mmap IPC first, fall back to file-based IPC
        output = self._call_mojo_mmap(input_data, timeout=10)
        if output is not None:
            return output

        try:
            # File-based IPC fallback (original approach)
            with tempfile.NamedTemporaryFile(mode='w', suffix='_in.json', delete=False) as f:
                temp_input = f.name
                json.dump(input_data, f)
            with tempfile.NamedTemporaryFile(mode='w', suffix='_out.json', delete=False) as f:
                temp_output = f.name

            result = subprocess.run(
                [self.binary_path, temp_input, temp_output],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                logger.error("Mojo execution failed: %s", result.stderr)
                return None
            with open(temp_output, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error("Mojo bridge error: %s", e)
            return None
        finally:
            for p in (temp_input, temp_output):
                try:
                    os.unlink(p)
                except OSError:
                    pass
    
    def compute_operator_scores(
        self,
        prices: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        opens: np.ndarray,
        closes: np.ndarray,
        volumes: np.ndarray
    ) -> Optional[List[float]]:
        """Call Mojo to compute 18-operator scores"""
        if not self.available:
            return None

        input_data = {
            'prices': prices.tolist(),
            'highs': highs.tolist(),
            'lows': lows.tolist(),
            'opens': opens.tolist(),
            'closes': closes.tolist(),
            'volumes': volumes.tolist(),
        }

        # T2-H: try mmap IPC first
        output = self._call_mojo_mmap(input_data, extra_args=["--operators"], timeout=5)
        if output is not None:
            return output.get('scores', [])

        # File-based fallback
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='_ops_in.json', delete=False) as f:
                temp_input = f.name
                json.dump(input_data, f)
            with tempfile.NamedTemporaryFile(mode='w', suffix='_ops_out.json', delete=False) as f:
                temp_output = f.name

            result = subprocess.run(
                [self.binary_path, '--operators', temp_input, temp_output],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return None
            with open(temp_output, 'r') as f:
                return json.load(f).get('scores', [])
        except Exception as e:
            logger.error("Mojo operators error: %s", e)
            return None
        finally:
            for p in (temp_input, temp_output):
                try:
                    os.unlink(p)
                except OSError:
                    pass


# Singleton
mojo_bridge = MojoEngineBridge()


def get_mojo_status() -> Dict:
    """Get Mojo availability status"""
    return {
        'available': MOJO_AVAILABLE,
        'binary_path': MOJO_BINARY_PATH,
        'version': '1.0.0' if MOJO_AVAILABLE else None
    }
