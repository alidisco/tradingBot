"""
bot_termux.py
Standalone Termux / Linux ARM64 Trading Bot for Gold (XAUUSD) on FTMO MT5.
Uses MetaApi Cloud SDK (Pure Python, runs natively on Android Termux without Windows).

Strategy:
- H1 Donchian 20-Bar Breakout + 2.5x ATR Trailing Stop
- FTMO 1.00% Risk Auto-Sizing
- Wednesday & Weak Close Filters
"""

import asyncio
import os
import sys
import datetime
import pandas as pd
import numpy as np
from metaapi_cloud_sdk import MetaApi

# ==========================================
# CONFIGURATION
# ==========================================
# 1. Get your free token from https://app.metaapi.cloud
API_TOKEN = os.getenv("METAAPI_TOKEN", "YOUR_METAAPI_TOKEN_HERE")

# 2. Your MetaApi Account ID (generated when you add your FTMO account on metaapi.cloud)
ACCOUNT_ID = os.getenv("METAAPI_ACCOUNT_ID", "YOUR_ACCOUNT_ID_HERE")

SYMBOL = "XAUUSD"
TIMEFRAME = "1h" # 1-Hour candles
ENTRY_PERIOD = 20
EXIT_PERIOD = 10
ATR_PERIOD = 14
TRAIL_ATR_MULT = 2.5
FTMO_RISK_PERCENT = 1.00 # 1.00% Sweet Spot
MAGIC_NUMBER = 889900
CHECK_INTERVAL_SECONDS = 60

async def main():
    if API_TOKEN == "YOUR_METAAPI_TOKEN_HERE" or ACCOUNT_ID == "YOUR_ACCOUNT_ID_HERE":
        print("\n" + "="*70)
        print(" [!] SETUP REQUIRED IN bot_termux.py:")
        print(" 1. Sign up for free at https://app.metaapi.cloud")
        print(" 2. Add your FTMO Demo account (Server: FTMO-Demo, Login, Password)")
        print(" 3. Copy your API Token and Account ID into bot_termux.py")
        print("="*70 + "\n")
        return

    print("Connecting to MetaApi on Termux...")
    api = MetaApi(API_TOKEN)
    account = await api.metatrader_account_api.get_account(ACCOUNT_ID)
    
    # Ensure account is deployed
    if account.state != 'DEPLOYED':
        print("Deploying account on cloud...")
        await account.deploy()
        
    print("Waiting for MT5 broker connection...")
    await account.wait_connected()
    connection = account.get_rpc_connection()
    await connection.connect()
    await connection.wait_synchronized()
    
    acc_info = await connection.get_account_information()
    print(f"Connected to FTMO! Server: {acc_info['server']} | Balance: ${acc_info['balance']:.2f} | Leverage: 1:{acc_info['leverage']}")
    
    last_candle_time = None
    
    while True:
        try:
            # Fetch recent H1 candles
            candles = await connection.get_historical_candles(SYMBOL, TIMEFRAME, datetime.datetime.now(), 60)
            if not candles or len(candles) < 30:
                await asyncio.sleep(15)
                continue
                
            df = pd.DataFrame(candles)
            df['datetime'] = pd.to_datetime(df['time'])
            
            # Check for new completed H1 candle
            current_bar_time = df['datetime'].iloc[-2]
            if current_bar_time != last_candle_time:
                last_candle_time = current_bar_time
                print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] New H1 Bar: {current_bar_time}. Analyzing TrendRunner...")
                
                # Indicators
                df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
                df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
                
                hl = df['high'] - df['low']
                hc = (df['high'] - df['close'].shift()).abs()
                lc = (df['low'] - df['close'].shift()).abs()
                df['atr'] = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(ATR_PERIOD).mean()
                
                completed_bar = df.iloc[-2]
                c1 = completed_bar['close']
                ema50 = completed_bar['ema_50']
                ema200 = completed_bar['ema_200']
                cur_atr = completed_bar['atr']
                
                # Check active positions
                positions = await connection.get_positions()
                bot_positions = [p for p in positions if p.get('symbol') == SYMBOL and p.get('magic') == MAGIC_NUMBER]
                
                # 1. Manage Active Position (Trailing Stop & Channel Exit)
                if bot_positions:
                    pos = bot_positions[0]
                    p_id = pos['id']
                    p_type = pos['type']
                    cur_sl = pos.get('stopLoss', 0.0)
                    
                    recent_10 = df.iloc[-EXIT_PERIOD-1:-1]
                    exit_low = recent_10['low'].min()
                    exit_high = recent_10['high'].max()
                    
                    if p_type == 'POSITION_TYPE_BUY':
                        if c1 <= exit_low:
                            print(f"Closing BUY position #{p_id} on 10-bar channel breakdown.")
                            await connection.close_position(p_id)
                        else:
                            new_sl = max(c1 - (TRAIL_ATR_MULT * cur_atr), exit_low)
                            if new_sl > (cur_sl + 0.50):
                                print(f"Trailing SL updated for BUY: {new_sl:.2f}")
                                await connection.modify_position(p_id, stop_loss=round(new_sl, 2))
                                
                    elif p_type == 'POSITION_TYPE_SELL':
                        if c1 >= exit_high:
                            print(f"Closing SELL position #{p_id} on 10-bar channel breakout.")
                            await connection.close_position(p_id)
                        else:
                            new_sl = min(c1 + (TRAIL_ATR_MULT * cur_atr), exit_high)
                            if cur_sl == 0.0 or new_sl < (cur_sl - 0.50):
                                print(f"Trailing SL updated for SELL: {new_sl:.2f}")
                                await connection.modify_position(p_id, stop_loss=round(new_sl, 2))
                                
                    await asyncio.sleep(CHECK_INTERVAL_SECONDS)
                    continue
                    
                # 2. Look for New Breakout Entry
                # Filter: Wednesday skip
                if completed_bar['datetime'].weekday() == 2:
                    print("Skipping entry: Wednesday filter active.")
                    await asyncio.sleep(CHECK_INTERVAL_SECONDS)
                    continue
                    
                bar_range = completed_bar['high'] - completed_bar['low']
                if bar_range <= 0 or np.isnan(cur_atr):
                    await asyncio.sleep(CHECK_INTERVAL_SECONDS)
                    continue
                    
                # 20-bar Donchian Entry Channel
                entry_bars = df.iloc[-ENTRY_PERIOD-1:-1]
                donchian_high = entry_bars['high'].iloc[:-1].max()
                donchian_low = entry_bars['low'].iloc[:-1].min()
                
                # Price quotes
                price_info = await connection.get_symbol_price(SYMBOL)
                ask = price_info['ask']
                bid = price_info['bid']
                
                # FTMO 1.00% Risk Lot Calculation
                acc_live = await connection.get_account_information()
                balance = acc_live['balance']
                risk_dollars = balance * (FTMO_RISK_PERCENT / 100.0)
                sl_dist = TRAIL_ATR_MULT * cur_atr
                # 100 oz contract size
                calc_lot = risk_dollars / (sl_dist * 100.0)
                calc_lot = round(round(calc_lot / 0.01) * 0.01, 2)
                lot = max(0.01, min(calc_lot, 10.0))
                
                # Bullish Breakout
                if c1 > donchian_high and ema50 > ema200:
                    strong_close = (c1 - completed_bar['low']) / bar_range >= 0.65
                    if strong_close:
                        sl = ask - sl_dist
                        print(f"EXECUTING FTMO BUY: {lot} lots @ {ask:.2f} | SL: {sl:.2f} (Risking 1% = ${risk_dollars:.2f})")
                        await connection.create_market_buy_order(SYMBOL, lot, stop_loss=round(sl, 2), magic=MAGIC_NUMBER)
                        
                # Bearish Breakout
                elif c1 < donchian_low and ema50 < ema200:
                    strong_close = (completed_bar['high'] - c1) / bar_range >= 0.65
                    if strong_close:
                        sl = bid + sl_dist
                        print(f"EXECUTING FTMO SELL: {lot} lots @ {bid:.2f} | SL: {sl:.2f} (Risking 1% = ${risk_dollars:.2f})")
                        await connection.create_market_sell_order(SYMBOL, lot, stop_loss=round(sl, 2), magic=MAGIC_NUMBER)
                        
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
            
        except Exception as e:
            print(f"Error in Termux bot loop: {e}")
            await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(main())
