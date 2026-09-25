"""
main.py
Gold H1 Trend-Runner - Live Terminal Execution & Visual Telemetry Dashboard for MetaTrader 5
Designed for FTMO Challenge (1.00% Risk Mode, Zero Cloud, 100% Local).

Usage:
    python main.py
"""

import sys
import os
import time
import datetime
import logging
import psutil
import MetaTrader5 as mt5
import pandas as pd
import numpy as np

# Force UTF-8 encoding on Windows consoles to prevent UnicodeEncodeError
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# ==============================================================================
# CONFIGURATION
# ==============================================================================
SYMBOL = "XAUUSD"
TIMEFRAME = mt5.TIMEFRAME_H1
MAGIC_NUMBER = 889900

# Strategy Parameters (The Institutional Sweet Spot)
ENTRY_PERIOD = 20           # 20-Hour Donchian Breakout
EXIT_PERIOD = 10            # 10-Hour Channel Exit
ATR_PERIOD = 14             # ATR Period
TRAIL_ATR_MULT = 2.5        # ATR Trailing Stop Multiplier
FAST_EMA_PERIOD = 50        # Fast Trend Filter (50 EMA)
SLOW_EMA_PERIOD = 200       # Slow Trend Filter (200 EMA)

USE_TREND_FILTER = True      # True: Require EMA 50 > EMA 200 for BUY / EMA 50 < EMA 200 for SELL (Recommended)
                            # False: Pure Turtle/Donchian Breakout (Trades any 20-bar channel breakout)
SKIP_WEDNESDAY = True       # Skip Wednesday (Avoid Midweek FOMC / Chop Trap)
STRONG_CLOSE_ONLY = True    # Require candle body to close in top/bottom 35% of range
MAX_SPREAD_POINTS = 75      # Max spread allowed (75 points = $0.75 on Gold; handles FTMO spreads)

# FTMO Money Management
FTMO_MODE = True            # Auto-calculate exact lot size for FTMO risk rule
FTMO_RISK_PERCENT = 1.00    # 1.00% Risk per trade (Institutional standard)
FIXED_LOT_FALLBACK = 0.01

CHECK_INTERVAL_SECONDS = 5  # Live telemetry update rate (every 5 seconds)

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.FileHandler("bot_execution.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)

def kill_previous_instances():
    """Ensure only one instance of main.py runs at a time."""
    current_pid = os.getpid()
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['pid'] != current_pid:
                cmd = proc.info.get('cmdline')
                if cmd and any('main.py' in str(c) for c in cmd):
                    logging.info(f"Terminating previous main.py instance (PID {proc.info['pid']})...")
                    proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

def initialize_mt5():
    """Connect to the running desktop MetaTrader 5 terminal."""
    if not mt5.initialize():
        logging.error(f"MT5 initialization failed: {mt5.last_error()}")
        logging.error("Make sure your MetaTrader 5 desktop application is open and logged in!")
        return False
        
    symbol_info = mt5.symbol_info(SYMBOL)
    if not symbol_info:
        logging.error(f"Symbol {SYMBOL} not found in MT5 Market Watch.")
        mt5.shutdown()
        return False
        
    if not symbol_info.visible:
        mt5.symbol_select(SYMBOL, True)
        
    account = mt5.account_info()
    if not account:
        logging.error("Failed to retrieve account details.")
        mt5.shutdown()
        return False
        
    return True

def fetch_data(count=80):
    """Retrieve historical rates and calculate indicators."""
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, count)
    if rates is None or len(rates) < 30:
        return None
        
    df = pd.DataFrame(rates)
    df['datetime'] = pd.to_datetime(df['time'], unit='s')
    
    # Calculate EMAs
    df['ema_50'] = df['close'].ewm(span=FAST_EMA_PERIOD, adjust=False).mean()
    df['ema_200'] = df['close'].ewm(span=SLOW_EMA_PERIOD, adjust=False).mean()
    
    # Calculate ATR
    hl = df['high'] - df['low']
    hc = (df['high'] - df['close'].shift()).abs()
    lc = (df['low'] - df['close'].shift()).abs()
    df['atr'] = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(ATR_PERIOD).mean()
    
    return df

def get_bot_positions():
    """Return all active positions managed by this bot."""
    positions = mt5.positions_get(symbol=SYMBOL)
    if not positions:
        return []
    return [p for p in positions if p.magic == MAGIC_NUMBER]

def manage_open_positions(df, new_candle_opened):
    """
    Manage active positions:
    - Trailing stop is evaluated on every tick.
    - Channel exit is evaluated when an H1 candle finishes.
    """
    bot_positions = get_bot_positions()
    if not bot_positions:
        return False
        
    pos = bot_positions[0]
    ticket = pos.ticket
    pos_type = pos.type
    current_sl = pos.sl
    current_price = pos.price_current
    profit = pos.profit
    
    # Exit channel based on completed bars
    recent_bars = df.iloc[-EXIT_PERIOD-1:-1]
    exit_low = recent_bars['low'].min()
    exit_high = recent_bars['high'].max()
    cur_atr = df['atr'].iloc[-2]
    cur_close = df['close'].iloc[-2]
    
    if pos_type == mt5.ORDER_TYPE_BUY:
        # Exit on 10-bar channel breakdown (only on completed candle)
        if new_candle_opened and cur_close <= exit_low:
            logging.info(f"🚨 [EXIT] Closing BUY #{ticket} @ {current_price:.2f} (10-bar exit low broken: {exit_low:.2f}). PnL: ${profit:+.2f}")
            close_position(pos)
            return True
            
        # Trailing stop update (can update anytime price advances)
        new_sl = max(cur_close - (TRAIL_ATR_MULT * cur_atr), exit_low)
        if new_sl > (current_sl + 0.50):
            modify_sl(ticket, new_sl)
            
    elif pos_type == mt5.ORDER_TYPE_SELL:
        # Exit on 10-bar channel breakout (only on completed candle)
        if new_candle_opened and cur_close >= exit_high:
            logging.info(f"🚨 [EXIT] Closing SELL #{ticket} @ {current_price:.2f} (10-bar exit high broken: {exit_high:.2f}). PnL: ${profit:+.2f}")
            close_position(pos)
            return True
            
        # Trailing stop update
        new_sl = min(cur_close + (TRAIL_ATR_MULT * cur_atr), exit_high)
        if current_sl == 0.0 or new_sl < (current_sl - 0.50):
            modify_sl(ticket, new_sl)
            
    return True

def close_position(pos):
    """Close an open position."""
    symbol_info = mt5.symbol_info(SYMBOL)
    price = symbol_info.bid if pos.type == mt5.ORDER_TYPE_BUY else symbol_info.ask
    order_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "position": pos.ticket,
        "symbol": SYMBOL,
        "volume": pos.volume,
        "type": order_type,
        "price": price,
        "deviation": 25,
        "magic": MAGIC_NUMBER,
        "comment": "TrendRunner_Exit",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC
    }
    res = mt5.order_send(request)
    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
        logging.info(f"Position #{pos.ticket} closed successfully.")
    else:
        # Fallback to FOK filling mode
        request["type_filling"] = mt5.ORDER_FILLING_FOK
        mt5.order_send(request)

def modify_sl(ticket, new_sl):
    """Update stop loss level."""
    symbol_info = mt5.symbol_info(SYMBOL)
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": ticket,
        "symbol": SYMBOL,
        "sl": round(new_sl, symbol_info.digits),
        "tp": 0.0
    }
    res = mt5.order_send(request)
    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
        logging.info(f"[TRAILING STOP] Position #{ticket} SL updated to {new_sl:.2f}")

def check_breakout_entry(df):
    """
    Evaluate breakout entry conditions when a candle finishes.
    Returns: True if evaluation completed (or skipped on valid rules),
             False if spread is temporarily too high and we should retry next tick.
    """
    symbol_info = mt5.symbol_info(SYMBOL)
    if not symbol_info:
        return False
        
    spread = symbol_info.spread
    if spread > MAX_SPREAD_POINTS:
        # Do not lock out the candle! Let it retry when spread cools down.
        logging.warning(f"Spread temporarily high ({spread} pts > {MAX_SPREAD_POINTS} limit). Retrying next tick...")
        return False
        
    completed_bar = df.iloc[-2]
    c1 = completed_bar['close']
    ema50 = completed_bar['ema_50']
    ema200 = completed_bar['ema_200']
    cur_atr = completed_bar['atr']
    bar_time = completed_bar['datetime']
    
    # 1. Skip Wednesday filter
    if SKIP_WEDNESDAY and bar_time.weekday() == 2:
        logging.info("[FILTER] Wednesday candle closed - skipped by midweek chop filter.")
        return True
        
    bar_range = completed_bar['high'] - completed_bar['low']
    if bar_range <= 0 or np.isnan(cur_atr):
        return True
        
    # 20 completed bars prior to the breakout candle
    entry_bars = df.iloc[-ENTRY_PERIOD-2 : -2]
    donchian_high = entry_bars['high'].max()
    donchian_low = entry_bars['low'].min()
    
    # Trend filter verification
    trend_ok_buy = (not USE_TREND_FILTER) or (ema50 > ema200)
    trend_ok_sell = (not USE_TREND_FILTER) or (ema50 < ema200)
    
    # Bullish Breakout Setup
    if c1 > donchian_high:
        if trend_ok_buy:
            strong_close = not STRONG_CLOSE_ONLY or ((c1 - completed_bar['low']) / bar_range >= 0.65)
            if strong_close:
                ask = symbol_info.ask
                sl_dist = TRAIL_ATR_MULT * cur_atr
                sl = ask - sl_dist
                execute_entry(mt5.ORDER_TYPE_BUY, ask, sl, sl_dist)
            else:
                logging.info(f"[FILTER] Bullish Breakout above {donchian_high:.2f} rejected: weak close wick (<65% of body).")
        else:
            logging.info(f"[FILTER] Bullish Breakout above {donchian_high:.2f} blocked by Bearish EMA 50/200 Trend Filter.")
            
    # Bearish Breakout Setup
    elif c1 < donchian_low:
        if trend_ok_sell:
            strong_close = not STRONG_CLOSE_ONLY or ((completed_bar['high'] - c1) / bar_range >= 0.65)
            if strong_close:
                bid = symbol_info.bid
                sl_dist = TRAIL_ATR_MULT * cur_atr
                sl = bid + sl_dist
                execute_entry(mt5.ORDER_TYPE_SELL, bid, sl, sl_dist)
            else:
                logging.info(f"[FILTER] Bearish Breakout below {donchian_low:.2f} rejected: weak close wick (<65% of body).")
        else:
            logging.info(f"[FILTER] Bearish Breakout below {donchian_low:.2f} blocked by Bullish EMA 50/200 Trend Filter.")
    else:
        logging.info(f"[SCAN] H1 Bar {bar_time} closed at {c1:.2f}. Inside 20h range ({donchian_low:.2f} - {donchian_high:.2f}). No breakout.")
        
    return True

def execute_entry(order_type, price, sl, sl_dist):
    """Calculate FTMO lot size and execute market order."""
    symbol_info = mt5.symbol_info(SYMBOL)
    account = mt5.account_info()
    
    trade_lot = FIXED_LOT_FALLBACK
    if FTMO_MODE and account:
        if sl_dist > 0:
            risk_dollars = account.balance * (FTMO_RISK_PERCENT / 100.0)
            contract_size = symbol_info.trade_contract_size
            calc_lot = risk_dollars / (sl_dist * contract_size)
            calc_lot = round(round(calc_lot / symbol_info.volume_step) * symbol_info.volume_step, 2)
            trade_lot = max(symbol_info.volume_min, min(calc_lot, symbol_info.volume_max))
            
    order_name = "BUY" if order_type == mt5.ORDER_TYPE_BUY else "SELL"
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": trade_lot,
        "type": order_type,
        "price": price,
        "sl": round(sl, symbol_info.digits),
        "tp": 0.0,
        "deviation": 25,
        "magic": MAGIC_NUMBER,
        "comment": f"FTMO_{order_name}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC
    }
    
    res = mt5.order_send(request)
    if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
        # Fallback to FOK filling mode
        request["type_filling"] = mt5.ORDER_FILLING_FOK
        res = mt5.order_send(request)
        if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
            request["type_filling"] = mt5.ORDER_FILLING_RETURN
            res = mt5.order_send(request)
            
    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
        risk_amt = account.balance * (FTMO_RISK_PERCENT / 100.0)
        logging.info(f"🚀 [ORDER EXECUTED] {order_name} {trade_lot} lots @ {price:.2f} | Initial SL: {sl:.2f} | Risk: {FTMO_RISK_PERCENT}% (${risk_amt:,.2f})")
    else:
        err = res.comment if res else mt5.last_error()
        logging.error(f"Failed to execute {order_name} order: {err}")

def print_live_dashboard(df):
    """Render a clean, comprehensive real-time terminal HUD."""
    account = mt5.account_info()
    symbol_info = mt5.symbol_info(SYMBOL)
    tick = mt5.symbol_info_tick(SYMBOL)
    if not account or not symbol_info or not tick:
        return
        
    bid = tick.bid
    ask = tick.ask
    spread = symbol_info.spread
    
    # Completed bar indicators
    c1 = df['close'].iloc[-2]
    ema50 = df['ema_50'].iloc[-2]
    ema200 = df['ema_200'].iloc[-2]
    atr_val = df['atr'].iloc[-2]
    trend_str = "BULLISH (50 > 200)" if ema50 > ema200 else "BEARISH (50 < 200)"
    
    # 20-hour Donchian Channel
    entry_bars = df.iloc[-ENTRY_PERIOD-1 : -1]
    donchian_high = entry_bars['high'].max()
    donchian_low = entry_bars['low'].min()
    
    dist_buy = max(0.0, donchian_high - ask)
    dist_sell = max(0.0, bid - donchian_low)
    
    # Countdown to next H1 candle close
    now = datetime.datetime.now()
    minutes_left = 59 - (now.minute % 60)
    seconds_left = 59 - (now.second % 60)
    
    spread_status = "✅ OK" if spread <= MAX_SPREAD_POINTS else f"⚠️ HIGH (> {MAX_SPREAD_POINTS})"
    
    # Active Positions
    bot_pos = get_bot_positions()
    pos_str = "NONE (Holding 100% Cash)"
    if bot_pos:
        p = bot_pos[0]
        p_type = "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL"
        pos_str = f"{p_type} #{p.ticket} ({p.volume} lots @ {p.price_open:.2f}) | Current: {p.price_current:.2f} | PnL: ${p.profit:+.2f} | SL: {p.sl:.2f}"
        
    # Reason / Status Diagnosis
    if bot_pos:
        status_reason = f"Managing active {p_type} trade with {TRAIL_ATR_MULT}x ATR trailing stop."
    elif dist_buy > 0 and dist_sell > 0:
        status_reason = f"Consolidating inside 20-hour channel (${donchian_low:.2f} - ${donchian_high:.2f}). No breakout yet."
    else:
        status_reason = "Breakout zone reached! Evaluating candle close confirmation."

    hud_text = (
        "\n" + "=" * 78 + "\n" +
        "           🏆 GOLD H1 TREND-RUNNER BOT (LIVE TELEMETRY HUD)\n" +
        "=" * 78 + "\n" +
        f" Account:  {account.login} ({account.server}) | Balance: ${account.balance:,.2f} | Equity: ${account.equity:,.2f}\n" +
        f" Market:   {SYMBOL} | Bid: {bid:.2f} | Ask: {ask:.2f} | Spread: {spread} pts ({spread_status})\n" +
        f" H1 Trend: {trend_str} | ATR(14): {atr_val:.2f} | Next Candle: ~{minutes_left:02d}m {seconds_left:02d}s\n" +
        "-" * 78 + "\n" +
        f" 🟢 BUY TRIGGER:  H1 Close > ${donchian_high:.2f}  (Distance: +${dist_buy:.2f})\n" +
        f" 🔴 SELL TRIGGER: H1 Close < ${donchian_low:.2f}  (Distance: -${dist_sell:.2f})\n" +
        f" Trend Filter:    {'ON (EMA 50/200 required)' if USE_TREND_FILTER else 'OFF (Pure Channel Breakout)'}\n" +
        f" Active Position: {pos_str}\n" +
        f" Current Status:  {status_reason}\n" +
        "=" * 78
    )
    print(hud_text, flush=True)

def run_bot():
    kill_previous_instances()
    
    if not initialize_mt5():
        return
        
    logging.info("Connected to MetaTrader 5 successfully!")
    logging.info("Starting live monitoring loop. Press Ctrl+C to stop.\n")
    
    last_candle_time = None
    last_hud_time = 0
    
    while True:
        try:
            df = fetch_data(count=80)
            if df is not None and len(df) > 0:
                cur_candle_time = df['datetime'].iloc[-1]
                new_candle_opened = (cur_candle_time != last_candle_time)
                
                # Manage positions (evaluated on every tick for trailing stop updates)
                has_open = manage_open_positions(df, new_candle_opened)
                
                # Check breakout entry on completed candle
                if new_candle_opened and not has_open:
                    eval_success = check_breakout_entry(df)
                    if eval_success:
                        last_candle_time = cur_candle_time
                        
                # Display Live Visual Dashboard every CHECK_INTERVAL_SECONDS
                now_ts = time.time()
                if now_ts - last_hud_time >= CHECK_INTERVAL_SECONDS:
                    last_hud_time = now_ts
                    print_live_dashboard(df)
                    
            time.sleep(1)
            
        except KeyboardInterrupt:
            logging.info("\nBot stopped by user. Shutting down connection...")
            break
        except Exception as e:
            logging.error(f"Unexpected error: {e}", exc_info=True)
            time.sleep(10)
            
    mt5.shutdown()
    logging.info("MetaTrader 5 connection closed cleanly.")

if __name__ == "__main__":
    run_bot()
