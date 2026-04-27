# ApexQuantumICT Trading Bot - Deployment Guide

## Platform Options

### Option 1: Heroku (Recommended)
Best for Python worker processes with free tier available.

**Steps:**
1. Install Heroku CLI: https://devcenter.heroku.com/articles/heroku-cli
2. Login: `heroku login`
3. Create app: `heroku create apexquantumict-bot`
4. Set environment variables:
   ```
   heroku config:set NVAPI_KEY=your_nvidia_api_key
   heroku config:set TELEGRAM_BOT_TOKEN=your_bot_token
   ```
5. Deploy: `git push heroku main`
6. Scale worker: `heroku ps:scale worker=1`

**Files already created:**
- `Procfile`: `web: gunicorn bot_server:app`
- `requirements.txt`: All dependencies
- `runtime.txt`: Python 3.11.5

### Option 2: Railway (Easiest)
Simplest deployment with automatic scaling.

**Steps:**
1. Go to https://railway.app
2. Connect GitHub repository
3. Add environment variables in dashboard:
   - `NVAPI_KEY`
   - `TELEGRAM_BOT_TOKEN`
4. Deploy automatically

### Option 3: Render
Reliable free tier for workers.

**Steps:**
1. Go to https://render.com
2. Create "Background Worker"
3. Connect repository
4. Set environment variables
5. Deploy

### Option 4: VPS (DigitalOcean, AWS, etc.)
Full control over the environment.

**Steps:**
1. SSH into server
2. Clone repository
3. Install Python 3.11
4. Create virtual environment
5. Install requirements
6. Set environment variables
7. Run with PM2 or systemd:
   ```bash
   pip install -r requirements.txt
   export NVAPI_KEY=your_key
   export TELEGRAM_BOT_TOKEN=your_token
   python -m apps.telegram.telegram_bot_full
   ```

## Environment Variables Required

| Variable | Description | Get From |
|----------|-------------|----------|
| `NVAPI_KEY` | NVIDIA API key | https://build.nvidia.com |
| `TELEGRAM_BOT_TOKEN` | Bot token | @BotFather on Telegram |

## Pre-Deployment Checklist

- [ ] `requirements.txt` includes all dependencies
- [ ] `Procfile` specifies correct command
- [ ] Environment variables configured
- [ ] Bot token obtained from @BotFather
- [ ] NVIDIA API key obtained
- [ ] Code pushed to Git repository

## Post-Deployment Verification

Test these commands in Telegram:
- `/start` - Should show welcome with trading commands
- `/market EURUSD` - Should run ICT analysis
- `/operators` - Should list 18 operators
- `/trading` - Should show system status

## Monitoring

Health check endpoint: `https://your-app-url.herokuapp.com/`
Returns: `{"status": "running", "trading_enabled": true, ...}`

## Troubleshooting

**Bot not responding:**
- Check `TELEGRAM_BOT_TOKEN` is correct
- Check logs: `heroku logs --tail`
- Verify bot isn't blocked by user

**Trading commands not working:**
- Check `NVAPI_KEY` is valid
- Verify `TRADING_AVAILABLE` is True in logs
- Check all trading modules imported successfully

**Import errors:**
- Verify `trading/` directory is in repository
- Check `__init__.py` files exist in all subdirectories

## Architecture

```
User → Telegram → Bot Server → NVIDIA AI / Trading System
                            ↓
                    Shadow Trading Loop
                            ↓
          18 Operators → Path Integral → Evidence Chain
```

## Support

For issues with:
- **NVIDIA API**: https://docs.nvidia.com/
- **python-telegram-bot**: https://docs.python-telegram-bot.org/
- **ApexQuantumICT**: Check system test with `python validation/legacy/test_full_system.py`
