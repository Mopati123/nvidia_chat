# Tutorials — ApexQuantumICT

Step-by-step guides for running the system.

---

## Prerequisites

- **Python 3.10+** — Required
- **pip** — For package installation
- **MetaTrader 5** — Optional; only needed for live/demo MT5 trading
- **Deriv account** — Optional; only needed for Deriv broker
- **NVIDIA API key** — Optional; only needed for Telegram AI bot
- **Telegram account** — Optional; only needed for bot control

---

## Installation

```bash
git clone https://github.com/Mopati123/nvidia_chat.git
cd nvidia_chat
pip install -r requirements.txt
```

Verify the core pipeline imports correctly:

```bash
python -c "from trading.pipeline.orchestrator import PipelineOrchestrator; print('OK')"
```

---

## Tutorial 1: Run Paper Trading (Zero Capital)

Paper trading runs the full 20-stage pipeline with simulated execution — no real money, no broker connection required.

### Step 1: Set minimum environment variables

```bash
# Windows
set MAX_RISK_PER_TRADE=0.02
set DAILY_LOSS_LIMIT=500

# Linux / macOS
export MAX_RISK_PER_TRADE=0.02
export DAILY_LOSS_LIMIT=500
```

### Step 2: Launch

```bash
python -m scripts.trading.start_paper_trading
```

### What to expect

```
[INFO] Starting ApexQuantumICT paper trading...
[INFO] Health monitoring started (30s interval)
[INFO] Generating 20 simulated signals for demo...
[INFO] Pipeline executed: EURUSD | decision=AUTHORIZED | PnL=$12.50
[INFO] Circuit breaker state: CLOSED | failures=0
[INFO] PnL divergence: 4.2% (below 15% threshold)
```

The system will:
1. Generate 20 mock OHLCV signals
2. Run each through the full 20-stage pipeline
3. Print collapse decisions (AUTHORIZED/REFUSED) and reasons
4. Track PnL and circuit breaker state
5. Run a 2-minute health monitoring loop, then gracefully shut down

### Reading the output

| Line | Meaning |
|------|---------|
| `decision=AUTHORIZED` | ExecutionToken issued, trade would execute |
| `decision=REFUSED` | One of 14 gates rejected the trade |
| `circuit_breaker=OPEN` | 10+ consecutive failures detected |
| `pnl_divergence=X%` | Predicted vs actual PnL gap (>15% triggers weight penalty) |

---

## Tutorial 2: Add Synthetic Order-Book Analytics

The order-book overlay is analytics-only. It lets the pipeline score depth pressure without connecting to Binance, IB, MT5 depth, Deriv depth, or any live execution surface.

```python
from trading.pipeline.orchestrator import PipelineOrchestrator

raw_data = {
    "ohlcv": [],
    "order_book": {
        "symbol": "EURUSD",
        "timestamp": 1.0,
        "bids": [
            {"price": 1.0998, "volume": 300},
            {"price": 1.0997, "volume": 200},
            {"price": 1.0996, "volume": 100},
        ],
        "asks": [
            {"price": 1.1002, "volume": 100},
            {"price": 1.1003, "volume": 100},
            {"price": 1.1004, "volume": 100},
        ],
    },
}

context = PipelineOrchestrator(use_microstructure=False).execute(
    raw_data,
    symbol="EURUSD",
    source="synthetic",
)
print(context.hft_signals)
```

Expected signals include `depth_imbalance`, `layering_score`, `enhanced_microprice`, `pressure_ratio`, `iceberg_probability`, `book_inversion`, and `cumulative_delta`.

Important: these signals can change scoring through optional `S_HFT`, but they do not authorize broker execution. Live and shadow execution still require scheduler-issued tokens.

---

## Tutorial 3: Replay Read-Only Order-Book Feeds

The feed layer converts live or replayed depth data into the same `OrderBookSnapshot` shape used by analytics. Fake and replay feeds are safe for CI because they never connect to brokers or execution APIs.

```python
import asyncio
from trading.microstructure import FakeOrderBookFeed

book = {
    "symbol": "BTCUSDT",
    "timestamp": 1.0,
    "bids": [["100.0", "2.0"]],
    "asks": [["100.5", "1.5"]],
}

async def main():
    feed = FakeOrderBookFeed([book], symbol="BTCUSDT")
    async for snapshot in feed.snapshots():
        print(snapshot.to_dict())
        print(feed.health_snapshot())
        break

asyncio.run(main())
```

`BinanceDepthFeed` is read-only and uses Binance public depth WebSockets. `IBDepthFeed` is a read-only callback bridge for IB/TWS market-depth updates. Neither adapter can place orders.

---

## Tutorial 4: Run A Sandbox HFT Order

Sandbox HFT execution requires a scheduler-issued `hft_execution` token. A normal `live_execution` token is refused.

```python
from core.authority import HFTExecutionScope, issue_hft_execution_token
from core.execution import HFTOrderRequest, HFTSandboxGateway
from trading.kernel.scheduler import Scheduler

scheduler = Scheduler()
scope = HFTExecutionScope(
    broker="fake",
    symbol="BTCUSDT",
    side="buy",
    max_notional=50.0,
    max_slippage_bps=2.0,
    max_order_count=2,
    ttl_seconds=60.0,
    strategy_id="depth_accumulation_demo",
    sandbox_only=True,
)
token = issue_hft_execution_token(scheduler, scope)

request = HFTOrderRequest(
    broker="fake",
    symbol="BTCUSDT",
    side="buy",
    quantity=0.1,
    price=100.0,
    max_slippage_bps=1.0,
    strategy_id="depth_accumulation_demo",
    idempotency_key="demo-001",
)

result = HFTSandboxGateway().execute(
    request,
    token=token,
    feed_health={"stale": False, "update_age_seconds": 0.1},
)
print(result.to_dict())
```

This records audit evidence but does not touch Binance, IB, MT5, Deriv, Telegram, or real broker routing.

---

## Tutorial 5: Code-Gated HFT Canary Routing

The canary layer is off by default. Real routing refuses unless all gates pass:

```text
ALLOW_REAL_TRADING=1
HFT_CANARY_ENABLED=1
HFT_SANDBOX_CERTIFICATION=trading_data/hft/sandbox_certification.json
HFT_CANARY_MAX_NOTIONAL=10
HFT_CANARY_DAILY_LOSS_CAP=5
HFT_CANARY_MAX_ACTIVE_SYMBOLS=1
HFT_CANARY_SYMBOL=BTCUSDT
```

The certification file is local-only and generated after sandbox validation:

```python
from core.execution import write_sandbox_certification

write_sandbox_certification("trading_data/hft/sandbox_certification.json")
```

Even with env gates enabled, the request still needs a non-sandbox `hft_execution` token, fresh feed health, canary limits, and kill switch clearance. Rollback writes audit evidence and activates the HFT kill switch:

```python
from core.execution import CodeGatedHFTGateway, BinanceHFTExecutionAdapter

gateway = CodeGatedHFTGateway(broker=BinanceHFTExecutionAdapter(client=None))
gateway.rollback("operator_requested")
```

Passing `client=None` keeps the adapter non-operational. Production clients must be injected locally and never committed.

---

## Tutorial 6: Run the Live Dashboard

The dashboard shows real-time PnL, regime, circuit breaker state, and a kill switch.

### Step 1: Launch

```bash
uvicorn trading.dashboard.app:app --host 0.0.0.0 --port 8080
```

### Step 2: Open in browser

Navigate to `http://localhost:8080`

The page auto-refreshes every 2 seconds.

### Reading the dashboard

| Metric | Description |
|--------|-------------|
| **Daily PnL** | Realized profit/loss since midnight UTC |
| **Win Rate** | Percentage of profitable trades today |
| **Sharpe** | Approximate intraday Sharpe ratio |
| **Max Drawdown** | Peak-to-trough loss today |
| **Regime** | Current market regime (TRENDING/RANGING/HIGH_VOL/CRISIS) |
| **Circuit Breaker** | CLOSED (normal) / OPEN (trading halted) / HALF_OPEN (recovering) |
| **Kill Switch** | OFF (normal) / ON (all trading stopped) |

### Triggering the kill switch via API

```bash
curl -X POST http://localhost:8080/kill
# {"status": "kill_switch_activated"}

curl -X POST http://localhost:8080/kill/release
# {"status": "kill_switch_released"}
```

---

## Tutorial 4: Connect to Deriv Broker

### Step 1: Get a Deriv API token

1. Log in at [app.deriv.com](https://app.deriv.com)
2. Go to **Account Settings → API Token**
3. Create a token with **Trade** and **Read** permissions
4. Note your **App ID** (visible in the same section)

### Step 2: Set environment variables

```bash
# Windows
set DERIV_APP_ID=your_app_id
set DERIV_API_TOKEN=your_token

# Linux / macOS
export DERIV_APP_ID=your_app_id
export DERIV_API_TOKEN=your_token
```

### Step 3: Verify connection

```python
import asyncio
from trading.brokers.deriv_broker import DerivBroker

broker = DerivBroker()
connected = broker.connect()
print("Connected:", connected)
```

Or from the command line:

```bash
python -c "
from trading.brokers.deriv_broker import DerivBroker
b = DerivBroker()
print('Deriv connected:', b.connect())
"
```

---

## Tutorial 5: Connect to MetaTrader 5

### Step 1: Install MetaTrader 5

Download from your broker or [metatrader5.com](https://www.metatrader5.com). Open a demo or live account.

### Step 2: Set environment variables

```bash
# Windows
set MT5_LOGIN=123456789
set MT5_PASSWORD=yourpassword
set MT5_SERVER=YourBroker-Demo

# Linux / macOS (requires MT5 via Wine or Windows VM)
export MT5_LOGIN=123456789
export MT5_PASSWORD=yourpassword
export MT5_SERVER=YourBroker-Demo
```

### Step 3: Verify connection

```bash
python -c "
from trading.brokers.mt5_broker import MT5Broker
b = MT5Broker()
print('MT5 connected:', b.connect())
"
```

---

## Tutorial 6: Run the Telegram Bot

The Telegram bot lets you control the system and ask questions using AI models (Falcon, Nemotron 70B, Qwen 2.5).

### Step 1: Create a Telegram bot

1. Open Telegram and search for `@BotFather`
2. Send `/newbot` and follow the prompts
3. Copy the **bot token** you receive

### Step 2: Get an NVIDIA API key

1. Sign up at [build.nvidia.com](https://build.nvidia.com)
2. Generate an API key under your account

### Step 3: Set environment variables

```bash
# Windows
set TELEGRAM_BOT_TOKEN=your_bot_token
set NVIDIA_API_KEY=your_nvidia_key

# Linux / macOS
export TELEGRAM_BOT_TOKEN=your_bot_token
export NVIDIA_API_KEY=your_nvidia_key
```

### Step 4: Launch

```bash
python -m apps.telegram.telegram_bot_full
```

### What the bot can do

- Answer questions about the trading system using AI
- Show live PnL, regime, and positions
- Trigger or release the kill switch
- Display recent trade history
- Explain circuit breaker status

---

## Tutorial 6: Run Integration Tests

```bash
# T2 enhancements (geodesic seeds, FAISS, PPO, async, dashboard, Mojo)
python -m pytest validation/legacy/test_t2_integration.py -v

# T3-A production hardening (circuit breaker, PnL divergence)
python -m pytest validation/legacy/test_t3a_integration.py -v

# Geometry unit tests
python -m pytest tests/unit/test_geometry/ -v

# TAEP unit tests
python -m pytest tests/taep/ -v

# Full test suite
python -m pytest tests/ -v

# Maintained tests plus selected legacy integration tests
python -m pytest tests/ validation/legacy/test_t2_integration.py validation/legacy/test_t3a_integration.py -v
```

Expected output for T3-A:

```
validation/legacy/test_t3a_integration.py::TestT3A1CircuitBreaker::test_circuit_breaker_exists_on_orchestrator PASSED
validation/legacy/test_t3a_integration.py::TestT3A1CircuitBreaker::test_ten_failures_open_circuit PASSED
...
20 passed in 0.94s
```

---

## Tutorial 7: Read the Cryptographic Audit Trail

Every trade decision is Ed25519-signed and Merkle-chained.

```python
from trading.evidence.evidence_chain import EvidenceChain

chain = EvidenceChain()

# Access the chain
for record in chain.get_chain():
    print(record['timestamp'], record['decision'], record['anchor_hash'][:16])

# Verify integrity
is_valid = chain.verify_chain()
print("Chain valid:", is_valid)
```

The `anchor_hash` is a SHA-256 Merkle root that chains each record to the previous one — any tampering breaks the chain.
