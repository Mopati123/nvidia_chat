# API Reference — ApexQuantumICT

Complete reference for all public classes and methods.

---

## PipelineOrchestrator

**File:** `trading/pipeline/orchestrator.py`

The master controller for the 20-stage canonical pipeline.

### Constructor

```python
PipelineOrchestrator(
    scheduler=None,          # TAEPScheduler instance; auto-created if None
    risk_manager=None,       # ProductionRiskManager instance; auto-created if None
    use_microstructure=True, # Enable OFI/microprice microstructure layer
    use_weight_learning=True # Enable PPO + backward weight adaptation
)
```

On init, also creates:
- `self.collapse_breaker` — CircuitBreaker("scheduler_collapse", failure_threshold=10)
- `self.divergence_history` — `deque(maxlen=100)` for PnL divergence tracking

### Methods

```python
execute(
    raw_data: Dict,          # OHLCV dict: {"open":[], "high":[], "low":[], "close":[], "volume":[], "time":[]}
    symbol: str,             # e.g. "EURUSD"
    source: str = "MT5",     # "MT5" | "Deriv" | "TradingView"
    adapted_params=None      # Optional RegimeParameters from regime detector
) -> PipelineContext
```

Runs all 20 stages. Returns a `PipelineContext` with `stage_history`, `collapse_decision`, `proposal`, and `execution_result` populated.

```python
get_statistics() -> Dict
# Returns: {"total_executions": int, "successful": int, "refused": int, "success_rate": float}
```

### PipelineContext (dataclass)

```python
@dataclass
class PipelineContext:
    symbol: str
    timestamp: float
    source: str                     # "MT5" | "Deriv" | "TradingView"
    raw_data: Dict                  # normalized OHLCV
    market_state: Dict              # microstructure output
    ict_geometry: Dict              # extracted ICT zones
    regime: MarketRegime            # TRENDING | RANGING | HIGH_VOL | CRISIS
    regime_params: RegimeParameters # trajectory_count, epsilon_scale, max_position_size
    trajectories: List[Dict]        # RK4-generated candidate paths
    admissible_paths: List[Dict]    # after constraint filtering
    action_scores: Dict             # S_L, S_T, S_E, S_R per path
    proposal: Dict                  # {direction, entry, stop, target, size, predicted_pnl}
    risk_check_passed: bool
    risk_check_message: str
    collapse_decision: str          # "AUTHORIZED" | "REFUSED"
    execution_result: Dict          # {order_id, entry_price, realized_pnl, status}
    stage_history: List[str]        # ordered list of completed stage names
    duration_ms: float              # total pipeline duration
```

---

## TAEPScheduler

**File:** `taep/scheduler/scheduler.py`

The sole collapse authority. No trade executes without a signed ExecutionToken.

### Methods

```python
authorize_collapse(
    proposal: Dict,                  # trade proposal dict
    projected_trajectories: List,    # filtered admissible trajectories
    delta_s: float,                  # trajectory energy variance (entropy gate)
    constraints_passed: bool,        # risk gate result
    reconciliation_clear: bool       # prior reconciliation clean
) -> Tuple[Decision, ExecutionToken]
# Decision: "AUTHORIZED" | "REFUSED"
# Raises on circuit breaker open (caught by orchestrator)
```

```python
update_action_weights(
    pnl: float,              # realized PnL (negative = penalty)
    delta_s: float,          # trajectory entropy
    status: str,             # "success" | "mismatch" | "refused"
    contrib: Dict,           # {"L": int, "T": int, "E": int, "R": int}  — path contributions (sum to 100)
    constraints_passed: bool,
    evidence_complete: bool
) -> None
# Updates w_L, w_T, w_E, w_R via backward law:
# J = α·PnL_norm + β·ΔS - γ·Mismatch
# w_new = Π_simplex(w_old + η·J·contributions)
```

### ExecutionToken (dataclass)

```python
@dataclass
class ExecutionToken:
    token_id: str      # UUID4
    signature: str     # Ed25519 HMAC signature
    issued_at: float   # Unix timestamp
    expires_at: float  # issued_at + 30s
    budget: float      # max trade size authorized
    operation: str     # "trade_execution"
```

---

## ProductionRiskManager

**File:** `trading/risk/risk_manager.py`

Thread-safe hard-stop enforcement. All limits checked before any trade.

### Constructor

```python
ProductionRiskManager(
    daily_loss_limit: float = 500.0,    # USD daily loss limit (env: DAILY_LOSS_LIMIT)
    max_position_size: float = 0.1,     # max lots per trade (env: MAX_RISK_PER_TRADE)
    max_positions_per_symbol: int = 1,
    max_correlated_exposure: float = 0.3,
    kill_switch_on: bool = False
)
```

### Methods

```python
check_all_limits(
    symbol: str,
    direction: str,    # "buy" | "sell"
    size: float,       # lots
    price: float
) -> RiskCheck
# Checks in order: kill_switch → daily_loss → position_size → per_symbol → correlation
# Returns on first failure
```

```python
trigger_kill_switch(reason: str = "manual") -> None
# Sets manual_kill_switch = True
# Broadcasts to all registered kill callbacks
# Logs CRITICAL
```

```python
set_regime_limits(regime_params: RegimeParameters) -> None
# Dynamically updates max_position_size and stop_loss_multiplier from regime
```

```python
get_status() -> Dict
# Returns: {
#   "level": "GREEN"|"YELLOW"|"RED"|"KILL",
#   "daily_pnl": float,
#   "open_positions": int,
#   "max_drawdown": float,
#   "trades_today": int,
#   "kill_switch": bool
# }
```

```python
register_breach_callback(callback: Callable) -> None
register_kill_callback(callback: Callable) -> None
```

### RiskCheck (dataclass)

```python
@dataclass
class RiskCheck:
    passed: bool
    level: RiskLevel      # GREEN | YELLOW | RED | KILL
    message: str
    metric: str           # which limit was checked
    value: float          # actual value
    limit: float          # configured limit
```

### Singleton

```python
from trading.risk.risk_manager import get_risk_manager
rm = get_risk_manager()
```

---

## DailyPnLTracker

**File:** `trading/risk/pnl_tracker.py`

Daily profit/loss tracking with persistence, auto-reset at midnight UTC, and execution error histogram.

### Constructor

```python
DailyPnLTracker(
    data_dir: str = "trading_data/pnl",  # JSON persistence directory
    auto_kill: bool = True               # trigger kill switch at daily_loss_limit
)
```

State is persisted to `{data_dir}/pnl_{YYYY-MM-DD}.json` and loaded on restart.

### Methods

```python
record_trade(trade: TradeRecord) -> None
# Appends trade, updates daily_pnl, checks kill switch, persists to disk
```

```python
record_execution_error(predicted_pnl: float, realized_pnl: float) -> None
# Records |predicted - realized| / max(|predicted|, 1.0) into execution_errors deque
```

```python
get_divergence_stats() -> Dict
# Returns: {"mean": float, "std": float, "p95": float, "count": int}
# Computed from rolling 100-trade execution_errors deque
```

```python
get_current_pnl(include_unrealized: bool = False) -> float
```

```python
get_daily_stats() -> Dict
# Returns: {
#   "date": "YYYY-MM-DD",
#   "daily_pnl": float,
#   "total_trades": int,
#   "winning_trades": int,
#   "losing_trades": int,
#   "win_rate": float,
#   "avg_win": float,
#   "avg_loss": float,
#   "max_drawdown": float,
#   "peak_pnl": float,
#   "sharpe_approx": float,
#   "remaining_limit": float,
#   "limit_breached": bool
# }
```

```python
get_trade_history(limit: int = 100) -> List[TradeRecord]
generate_daily_report() -> str    # ASCII formatted report
```

### TradeRecord (dataclass)

```python
@dataclass
class TradeRecord:
    trade_id: str
    symbol: str
    direction: str         # "buy" | "sell"
    entry_price: float
    exit_price: float
    size: float            # lots
    realized_pnl: float    # USD
    entry_time: float      # Unix timestamp
    exit_time: float
    broker: str            # "mt5" | "deriv" | "tradingview"
    metadata: Dict

    @property
    def duration_seconds(self) -> float: ...
    @property
    def return_pct(self) -> float: ...
```

### Singleton

```python
from trading.risk.pnl_tracker import get_pnl_tracker
pt = get_pnl_tracker()
```

---

## CircuitBreaker

**File:** `trading/resilience/circuit_breaker.py`

CLOSED → OPEN → HALF_OPEN state machine wrapping Stage 15.

### Config

```python
@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 10     # consecutive failures to open
    success_threshold: int = 3      # consecutive successes to close from HALF_OPEN
    timeout_seconds: float = 30.0   # auto-transition OPEN → HALF_OPEN
```

### Methods

```python
call(fn: Callable, *args, **kwargs) -> Tuple[bool, Any]
# ok=True: circuit CLOSED/HALF_OPEN, fn executed, returns (True, result)
# ok=False: circuit OPEN, fn NOT called, returns (False, error_message)

register_on_open(callback: Callable) -> None   # fires when circuit transitions to OPEN
manual_close() -> None                          # force CLOSED (testing/recovery)
```

### States

```python
class CircuitState(Enum):
    CLOSED    = "closed"      # normal operation
    OPEN      = "open"        # all calls rejected
    HALF_OPEN = "half_open"   # testing recovery
```

### Singleton

```python
from trading.resilience.circuit_breaker import get_circuit_breaker, CircuitBreakerConfig
cb = get_circuit_breaker("scheduler_collapse")
print(cb.state.value, cb.failure_count)
```

---

## Brokers

### DerivBroker

**File:** `trading/brokers/deriv_broker.py`

```python
DerivBroker(api_token: str = None)   # or set DERIV_API_TOKEN env var
```

| Method | Description |
|--------|-------------|
| `connect() -> bool` | Open WebSocket to Deriv |
| `disconnect() -> None` | Close connection |
| `authorize(token: str) -> bool` | Send authorize request |
| `subscribe_ticks(symbol: str) -> None` | Stream tick data |
| `get_latest_tick() -> Optional[Dict]` | Latest tick (thread-safe) |
| `place_order(symbol, direction, amount, duration) -> Dict` | Submit trade |

### MT5Broker

**File:** `trading/brokers/mt5_broker.py`

```python
MT5Broker(
    account: int = None,    # or set MT5_LOGIN env var
    password: str = None,   # or set MT5_PASSWORD env var
    server: str = None      # or set MT5_SERVER env var
)
```

| Method | Description |
|--------|-------------|
| `connect(max_retries=5, retry_delay=3.0) -> bool` | Connect with retry logic |
| `disconnect() -> None` | Shutdown MT5 |
| `get_current_price(symbol: str) -> Optional[float]` | Latest bid |
| `place_order(symbol, direction, lots, sl_pips, tp_pips) -> Dict` | Send order |
| `get_open_positions() -> List[Dict]` | All open positions |

---

## FastAPI Dashboard

**File:** `trading/dashboard/app.py`

```bash
uvicorn trading.dashboard.app:app --host 0.0.0.0 --port 8080
```

### Endpoints

#### `GET /`
Returns HTML dashboard (auto-polls `/metrics` every 2 seconds).

#### `GET /metrics`
```json
{
  "daily_pnl": -12.50,
  "win_rate": 0.62,
  "sharpe": 1.34,
  "max_drawdown": 45.00,
  "regime": "TRENDING",
  "kill_switch": false,
  "circuit_breaker": "closed",
  "pnl_history": [0.0, 12.5, 8.3, -3.1]
}
```

#### `POST /kill`
Triggers kill switch. Returns:
```json
{"status": "kill_switch_activated"}
```

#### `POST /kill/release`
Releases kill switch. Returns:
```json
{"status": "kill_switch_released"}
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `APEX_SIGNING_KEY` | — | Ed25519 private key PEM (never commit) |
| `MT5_LOGIN` | — | MetaTrader 5 account number |
| `MT5_PASSWORD` | — | MetaTrader 5 password |
| `MT5_SERVER` | — | MetaTrader 5 broker server name |
| `DERIV_APP_ID` | — | Deriv application ID |
| `DERIV_API_TOKEN` | — | Deriv API token |
| `NVIDIA_API_KEY` | — | NVIDIA API key (Telegram bot AI models) |
| `TELEGRAM_BOT_TOKEN` | — | Telegram bot token from @BotFather |
| `MAX_RISK_PER_TRADE` | `0.02` | Max fraction of account per trade |
| `DAILY_LOSS_LIMIT` | `500` | Daily loss limit in USD |
| `APEX_CREDENTIAL_PASSWORD` | — | Credential encryption password |
