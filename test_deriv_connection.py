#!/usr/bin/env python3
"""
Deriv API Connection Test

Verifies the Deriv WebSocket connection and token authentication.
"""

import asyncio
import websockets
import json
import sys
import os

print('='*70)
print('DERIV WEBSOCKET CONNECTION TEST')
print('='*70)

# Load token
if not os.getenv('DERIV_API_TOKEN'):
    # Load from .env
    with open('.env', 'r') as f:
        for line in f:
            if line.startswith('DERIV_API_TOKEN='):
                token = line.strip().split('=', 1)[1]
                os.environ['DERIV_API_TOKEN'] = token
                break

token = os.getenv('DERIV_API_TOKEN')
if not token:
    print('❌ DERIV_API_TOKEN not found')
    sys.exit(1)

print(f'Token: {token[:15]}...')

async def test_deriv():
    uri = 'wss://ws.derivws.com/websockets/v3?app_id=1089'
    
    try:
        async with websockets.connect(uri) as websocket:
            print('✅ WebSocket connected')
            
            # Authorize
            auth_msg = {'authorize': token}
            await websocket.send(json.dumps(auth_msg))
            
            response = await websocket.recv()
            data = json.loads(response)
            
            if 'error' in data:
                print('❌ Authorization failed')
                print('   Error:', data['error'].get('message', 'Unknown error'))
                return False
            
            if 'authorize' in data:
                loginid = data['authorize'].get('loginid', 'N/A')
                balance = data['authorize'].get('balance', 'N/A')
                currency = data['authorize'].get('currency', 'N/A')
                
                print('✅ Authorized successfully')
                print(f'   Login ID: {loginid}')
                print(f'   Balance: {balance} {currency}')
                
                # Subscribe to ticks
                tick_msg = {
                    'ticks': 'R_100',
                    'subscribe': 1
                }
                await websocket.send(json.dumps(tick_msg))
                
                # Wait for tick
                tick_response = await asyncio.wait_for(websocket.recv(), timeout=10)
                tick_data = json.loads(tick_response)
                
                if 'tick' in tick_data:
                    quote = tick_data['tick'].get('quote', 'N/A')
                    print(f'✅ Tick data received: {quote}')
                
                return True
            else:
                print('❌ Unexpected response:', data)
                return False
            
    except Exception as e:
        print(f'❌ Connection error: {e}')
        return False

# Run test
result = asyncio.run(test_deriv())

if result:
    print('\n✅ DERIV CONNECTION TEST: PASSED')
    sys.exit(0)
else:
    print('\n❌ DERIV CONNECTION TEST: FAILED')
    sys.exit(1)
