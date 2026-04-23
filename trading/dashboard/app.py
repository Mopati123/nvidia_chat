"""
Real-Time Trading Dashboard  (T2-G)

FastAPI service exposing live system metrics and a browser dashboard.

Endpoints:
    GET  /           HTML dashboard (polls /metrics every 2 s)
    GET  /metrics    JSON snapshot: PnL, regime, Sharpe, drawdown, kill-switch state
    POST /kill       Activate risk_manager kill switch

Run:
    uvicorn trading.dashboard.app:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

logger = logging.getLogger(__name__)

app = FastAPI(title="ApexQuantumICT Dashboard", version="1.0")


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------

def _get_metrics() -> Dict[str, Any]:
    """Collect a live snapshot from all available subsystems."""
    metrics: Dict[str, Any] = {}

    try:
        from trading.risk.risk_manager import get_risk_manager
        rm = get_risk_manager()
        metrics["risk_status"] = rm.get_status()
        metrics["kill_switch"] = bool(rm.manual_kill_switch)
    except Exception as exc:
        logger.debug("risk_manager unavailable: %s", exc)
        metrics["risk_status"] = {}
        metrics["kill_switch"] = False

    try:
        from trading.risk.pnl_tracker import get_pnl_tracker
        pt = get_pnl_tracker()
        stats = pt.get_daily_stats()
        metrics["daily_pnl"] = stats.get("daily_pnl", 0.0)
        metrics["win_rate"]   = stats.get("win_rate", 0.0)
        metrics["max_drawdown"] = stats.get("max_drawdown", 0.0)
        metrics["sharpe"]     = stats.get("sharpe_approx", 0.0)
        metrics["total_trades"] = stats.get("total_trades", 0)
        # last 100 closed trades for PnL curve
        history = pt.get_trade_history(limit=100)
        metrics["pnl_history"] = [t.realized_pnl for t in history]
    except Exception as exc:
        logger.debug("pnl_tracker unavailable: %s", exc)
        metrics.setdefault("daily_pnl", 0.0)
        metrics.setdefault("pnl_history", [])

    # Regime from orchestrator context if available
    try:
        from trading.pipeline.orchestrator import get_orchestrator
        orch = get_orchestrator()
        ctx = getattr(orch, "_last_context", None)
        if ctx and hasattr(ctx, "regime") and ctx.regime:
            metrics["regime"] = ctx.regime.value
        else:
            metrics["regime"] = "UNKNOWN"
    except Exception:
        metrics["regime"] = "UNKNOWN"

    return metrics


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/metrics", response_class=JSONResponse)
def get_metrics_endpoint() -> Dict[str, Any]:
    """Return live system metrics as JSON."""
    return _get_metrics()


@app.post("/kill")
def kill_switch() -> Dict[str, str]:
    """Activate the emergency kill switch on the risk manager."""
    try:
        from trading.risk.risk_manager import get_risk_manager
        get_risk_manager().trigger_kill_switch("dashboard")
        logger.warning("Kill switch activated via dashboard")
        return {"status": "kill_switch_activated"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/kill/release")
def release_kill_switch() -> Dict[str, str]:
    """Release the kill switch (use with caution)."""
    try:
        from trading.risk.risk_manager import get_risk_manager
        get_risk_manager().release_kill_switch()
        return {"status": "kill_switch_released"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/prometheus", response_class=PlainTextResponse)
def prometheus_metrics() -> str:
    """Prometheus-format metrics for all 20 pipeline stages and system state."""
    try:
        from trading.observability.metrics import MetricsCollector
        return MetricsCollector.get().to_prometheus()
    except Exception as exc:
        logger.warning("Prometheus metrics unavailable: %s", exc)
        return "# metrics unavailable\n"


@app.get("/metrics/summary", response_class=JSONResponse)
def metrics_summary() -> Dict[str, Any]:
    """Stage latency summary and decision counts as JSON."""
    try:
        from trading.observability.metrics import MetricsCollector
        return MetricsCollector.get().summary()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    """Serve the browser dashboard."""
    return _HTML_TEMPLATE


# ---------------------------------------------------------------------------
# Inline HTML + JS template
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>ApexQuantumICT Dashboard</title>
<style>
  body { font-family: monospace; background: #0d0d0d; color: #00ff88; margin: 0; padding: 20px; }
  h1   { color: #00ccff; border-bottom: 1px solid #00ccff; padding-bottom: 8px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin: 20px 0; }
  .card { background: #111; border: 1px solid #222; border-radius: 6px; padding: 16px; }
  .card h3 { margin: 0 0 8px; color: #888; font-size: 12px; text-transform: uppercase; }
  .card .val { font-size: 28px; font-weight: bold; }
  .green { color: #00ff88; }
  .red   { color: #ff3333; }
  .yellow{ color: #ffcc00; }
  .regime { font-size: 22px; }
  #kill-btn { background: #ff3333; color: white; border: none; padding: 10px 28px;
              font-size: 16px; cursor: pointer; border-radius: 4px; margin-top: 8px; }
  #kill-btn:hover { background: #cc0000; }
  #status { margin-top: 8px; font-size: 12px; color: #666; }
  canvas { width: 100%; height: 120px; display: block; background: #0a0a0a;
           border: 1px solid #222; border-radius: 4px; }
</style>
</head>
<body>
<h1>ApexQuantumICT  &mdash;  Live Dashboard</h1>

<div class="grid">
  <div class="card">
    <h3>Daily PnL</h3>
    <div class="val" id="daily-pnl">—</div>
  </div>
  <div class="card">
    <h3>Win Rate</h3>
    <div class="val" id="win-rate">—</div>
  </div>
  <div class="card">
    <h3>Sharpe (approx)</h3>
    <div class="val" id="sharpe">—</div>
  </div>
  <div class="card">
    <h3>Max Drawdown</h3>
    <div class="val" id="drawdown">—</div>
  </div>
  <div class="card">
    <h3>Regime</h3>
    <div class="val regime" id="regime">—</div>
  </div>
  <div class="card">
    <h3>Kill Switch</h3>
    <div class="val" id="kill-state">—</div>
    <button id="kill-btn" onclick="activateKill()">KILL</button>
  </div>
</div>

<div style="margin-top:16px">
  <h3 style="color:#888;font-size:12px;text-transform:uppercase">PnL Curve (last 100 trades)</h3>
  <canvas id="pnl-chart"></canvas>
</div>

<div id="status">Connecting…</div>

<script>
async function fetchMetrics() {
  try {
    const r = await fetch('/metrics');
    const d = await r.json();

    const pnl = d.daily_pnl ?? 0;
    document.getElementById('daily-pnl').textContent = '$' + pnl.toFixed(2);
    document.getElementById('daily-pnl').className = 'val ' + (pnl >= 0 ? 'green' : 'red');

    const wr = (d.win_rate ?? 0) * 100;
    document.getElementById('win-rate').textContent = wr.toFixed(1) + '%';
    document.getElementById('win-rate').className = 'val ' + (wr >= 50 ? 'green' : 'yellow');

    const sh = d.sharpe ?? 0;
    document.getElementById('sharpe').textContent = sh.toFixed(2);
    document.getElementById('sharpe').className = 'val ' + (sh >= 1 ? 'green' : sh >= 0 ? 'yellow' : 'red');

    const dd = d.max_drawdown ?? 0;
    document.getElementById('drawdown').textContent = '$' + dd.toFixed(2);
    document.getElementById('drawdown').className = 'val red';

    document.getElementById('regime').textContent = d.regime ?? '—';

    const ks = d.kill_switch;
    document.getElementById('kill-state').textContent = ks ? 'ACTIVE' : 'OFF';
    document.getElementById('kill-state').className = 'val ' + (ks ? 'red' : 'green');

    drawPnL(d.pnl_history ?? []);

    document.getElementById('status').textContent =
      'Updated ' + new Date().toLocaleTimeString();
  } catch(e) {
    document.getElementById('status').textContent = 'Error: ' + e;
  }
}

function drawPnL(history) {
  const canvas = document.getElementById('pnl-chart');
  const ctx = canvas.getContext('2d');
  canvas.width = canvas.offsetWidth;
  canvas.height = 120;
  if (!history || history.length < 2) return;

  // Cumulative sum
  const cum = [];
  let running = 0;
  for (const v of history) { running += v; cum.push(running); }

  const mn = Math.min(...cum), mx = Math.max(...cum);
  const range = mx - mn || 1;

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.beginPath();
  ctx.strokeStyle = cum[cum.length-1] >= 0 ? '#00ff88' : '#ff3333';
  ctx.lineWidth = 1.5;
  cum.forEach((v, i) => {
    const x = (i / (cum.length - 1)) * canvas.width;
    const y = canvas.height - ((v - mn) / range) * (canvas.height - 10) - 5;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.stroke();
}

async function activateKill() {
  if (!confirm('Activate emergency kill switch?')) return;
  await fetch('/kill', {method: 'POST'});
  await fetchMetrics();
}

// Poll every 2 seconds
fetchMetrics();
setInterval(fetchMetrics, 2000);
</script>
</body>
</html>"""
