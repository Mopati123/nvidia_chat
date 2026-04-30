# Quick Deploy Guide - ApexQuantumICT Trading Bot

## Option 1: Heroku (Recommended - 2 minutes)

```bash
# 1. Install Heroku CLI and login
heroku login

# 2. Create app
heroku create your-bot-name

# 3. Set environment variables
heroku config:set NVAPI_KEY=your_nvidia_key
heroku config:set TELEGRAM_BOT_TOKEN=your_bot_token
heroku config:set DERIV_API_TOKEN=your_deriv_token  # Optional
heroku config:set MAX_DAILY_LOSS=100
heroku config:set MAX_POSITION_SIZE=0.1

# 4. Deploy
git push heroku main

# 5. Scale worker
heroku ps:scale worker=1
```

**Get your tokens:**
- **NVIDIA API**: https://build.nvidia.com
- **Telegram Bot**: Message @BotFather on Telegram
- **Deriv API**: https://app.deriv.com/account/api-token

## Option 2: Railway (Easiest - 1 minute)

1. Go to https://railway.app
2. Click "New Project" → "Deploy from GitHub repo"
3. Select your repository
4. Add environment variables in dashboard
5. Deploy automatically

## Option 3: Render

1. Go to https://render.com
2. Create "Background Worker"
3. Connect GitHub repository
4. Set environment variables
5. Deploy

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome menu |
| `/market EURUSD` | ICT + order-book analysis with 25 operators |
| `/shadow EURUSD bullish` | Shadow trade (simulation) |
| `/operators` | List all 25 operators |
| `/trading` | System status |
| `/mode [shadow/demo/live]` | Set trading mode |
| `/connect mt5` / `/connect deriv` | Connect broker |
| `/trade EURUSD buy 0.01` | Execute trade |
| `/positions` | Show open positions |

## System Features

- **NVIDIA AI**: Falcon 3, Nemotron 70B, Qwen models
- **18 ICT Operators**: FVG, OB, LP, OTE, sweep, displacement, etc.
- **Real Market Data**: Yahoo Finance (forex, crypto, stocks)
- **MT5 Integration**: Direct trading via MetaTrader 5
- **Deriv Integration**: WebSocket API for synthetics/options
- **Risk Management**: Daily loss limits, position sizing
- **Demo Mode**: Practice with fake money
- **Shadow Mode**: Full simulation with evidence
- **Live Mode**: Real capital (use with caution)

## System Invariants

- **Refusal-first**: Default non-execution
- **Scheduler sovereignty**: No entity can force collapse
- **Deterministic evidence**: Merkle + Ed25519 signatures
- **No sideways imports**: All coupling via OperatorMeta

## Support

For issues:
- Check logs: `heroku logs --tail`
- Verify tokens are correct
- Ensure all environment variables set
- Test with `/trading` command

## ⚠️ Risk Warning

- Always test in `demo` mode first
- Start with small positions
- Set strict risk limits
- Never risk more than you can afford to lose
- Trading involves substantial risk of loss
