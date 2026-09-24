"""
main.py
Gold H1 Trend-Runner - Live Terminal Execution for MetaTrader 5
Designed for FTMO Challenge (1.00% Risk Mode, Zero Cloud, 100% Local).

Usage:
    python main.py
"""

import sys
import time
import datetime
import logging
import MetaTrader5 as mt5
import pandas as pd
import numpy as np

# ==============================================================================
# CONFIGURATION
# ==============================================================================
SYMBOL = "XAUUSD"
TIMEFRAME = mt5.TIMEFRAME_H1
MAGIC_NUMBER = 889900

# Strategy Parameters (The Sweet Spot)
ENTRY_PERIOD = 20           # 20-Hour Donchian Breakout
EXIT_PERIOD = 10            # 10-Hour Channel Exit
ATR_PERIOD = 14             # ATR Period
TRAIL_ATR_MULT = 2.5        # ATR Trailing Stop Multiplier
FAST_EMA_PERIOD = 50        # Fast Trend Filter
SLOW_EMA_PERIOD = 200       # Slow Trend Filter

# Filters
SKIP_WEDNESDAY = True       # Skip Wednesday (Midweek/FOMC Chop)
STRONG_CLOSE_ONLY = True    # Require candle body to close in top/bottom 35%
MAX_SPREAD_POINTS = 60      # Max spread allowed (60 points = $0.60)

# FTMO Money Management
FTMO_MODE = True            # Auto-calculate exact lot size
FTMO_RISK_PERCENT = 1.00    # 1.00% Risk per trade
FIXED_LOT_FALLBACK = 0.01

CHECK_INTERVAL_SECONDS = 20

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

def print_banner():
    print("=" * 75)
    print("      🏆 GOLD H1 TREND-RUNNER BOT (METATRADER 5 & FTMO READY)")
    print("=" * 75)
    print(f" Symbol: {SYMBOL} | Timeframe: H1 (1-Hour)")
    print(f" Risk per trade: {FTMO_RISK_PERCENT}% (FTMO 1% Sweet Spot Mode)")
    print(f" Entry Channel: {ENTRY_PERIOD}h Breakout | Trailing Stop: {TRAIL_ATR_MULT}x ATR")
    print(f" Filters: Skip Wednesday = {SKIP_WEDNESDAY} | Strong Close Only = {STRONG_CLOSE_ONLY}")
    print("=" * 75)

def initialize_mt5():
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
        
    print(f"\n[+] Connected to MT5 Successfully!")
    print(f"    Account:  {account.login} ({account.server})")
    print(f"    Balance:  ${account.balance:,.2f} | Equity: ${account.equity:,.2f}")
    print(f"    Leverage: 1:{account.leverage} | Margin Free: ${account.margin_free:,.2f}")
    print(f"    Symbol:   {SYMBOL} (Digits: {symbol_info.digits}, Contract: {symbol_info.trade_contract_size} oz)\n")
    return True

def fetch_data(count=80):
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
    positions = mt5.positions_get(symbol=SYMBOL)
    if not positions:
        return []
    return [p for p in positions if p.magic == MAGIC_NUMBER]

def manage_open_positions(df):
    bot_positions = get_bot_positions()
    if not bot_positions:
        return False
        
    pos = bot_positions[0]
    ticket = pos.ticket
    pos_type = pos.type
    current_sl = pos.sl
    open_price = pos.price_open
    current_price = pos.price_current
    profit = pos.profit
    
    recent_bars = df.iloc[-EXIT_PERIOD-1:-1]
    exit_low = recent_bars['low'].min()
    exit_high = recent_bars['high'].max()
    cur_atr = df['atr'].iloc[-2]
    cur_close = df['close'].iloc[-2]
    
    if pos_type == mt5.ORDER_TYPE_BUY:
        # Exit on 10-bar channel breakdown
        if cur_close <= exit_low:
            logging.info(f"[EXIT] Closing BUY #{ticket} @ {current_price:.2f} (10-bar exit low broken). PnL: ${profit:+.2f}")
            close_position(pos)
            return True
            
        # Trailing stop
        new_sl = max(cur_close - (TRAIL_ATR_MULT * cur_atr), exit_low)
        if new_sl > (current_sl + 0.50):
            modify_sl(ticket, new_sl)
            
    elif pos_type == mt5.ORDER_TYPE_SELL:
        # Exit on 10-bar channel breakout
        if cur_close >= exit_high:
            logging.info(f"[EXIT] Closing SELL #{ticket} @ {current_price:.2f} (10-bar exit high broken). PnL: ${profit:+.2f}")
            close_position(pos)
            return True
            
        # Trailing stop
        new_sl = min(cur_close + (TRAIL_ATR_MULT * cur_atr), exit_high)
        if current_sl == 0.0 or new_sl < (current_sl - 0.50):
            modify_sl(ticket, new_sl)
            
    return True

def close_position(pos):
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
        "deviation": 20,
        "magic": MAGIC_NUMBER,
        "comment": "TrendRunner_Exit",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC
    }
    res = mt5.order_send(request)
    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
        logging.info(f"Position #{pos.ticket} closed successfully.")
    else:
        # Try FOK fallback
        request["type_filling"] = mt5.ORDER_FILLING_FOK
        mt5.order_send(request)

def modify_sl(ticket, new_sl):
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
    symbol_info = mt5.symbol_info(SYMBOL)
    if not symbol_info:
        return
        
    spread = symbol_info.spread
    if spread > MAX_SPREAD_POINTS:
        logging.warning(f"Spread high ({spread} pts > {MAX_SPREAD_POINTS} max). Entry paused.")
        return
        
    completed_bar = df.iloc[-2]
    c1 = completed_bar['close']
    ema50 = completed_bar['ema_50']
    ema200 = completed_bar['ema_200']
    cur_atr = completed_bar['atr']
    bar_time = completed_bar['datetime']
    
    # 1. Skip Wednesday filter
    if SKIP_WEDNESDAY and bar_time.weekday() == 2:
        return
        
    bar_range = completed_bar['high'] - completed_bar['low']
    if bar_range <= 0 or np.isnan(cur_atr):
        return
        
    # 20-bar Donchian Entry Channel
    entry_bars = df.iloc[-ENTRY_PERIOD-1:-1]
    donchian_high = entry_bars['high'].iloc[:-1].max()
    donchian_low = entry_bars['low'].iloc[:-1].min()
    
    # Bullish Breakout Setup
    if c1 > donchian_high and ema50 > ema200:
        strong_close = not STRONG_CLOSE_ONLY or ((c1 - completed_bar['low']) / bar_range >= 0.65)
        if strong_close:
            ask = symbol_info.ask
            sl_dist = TRAIL_ATR_MULT * cur_atr
            sl = ask - sl_dist
            execute_entry(mt5.ORDER_TYPE_BUY, ask, sl, sl_dist)
            
    # Bearish Breakout Setup
    elif c1 < donchian_low and ema50 < ema200:
        strong_close = not STRONG_CLOSE_ONLY or ((completed_bar['high'] - c1) / bar_range >= 0.65)
        if strong_close:
            bid = symbol_info.bid
            sl_dist = TRAIL_ATR_MULT * cur_atr
            sl = bid + sl_dist
            execute_entry(mt5.ORDER_TYPE_SELL, bid, sl, sl_dist)

def execute_entry(order_type, price, sl, sl_dist):
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
        "deviation": 20,
        "magic": MAGIC_NUMBER,
        "comment": f"FTMO_{order_name}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC
    }
    
    res = mt5.order_send(request)
    if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
        # Fallback filling mode
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

def run_bot():
    print_banner()
    if not initialize_mt5():
        return
        
    last_candle_time = None
    logging.info("Bot is active and monitoring market. Press Ctrl+C to stop.\n")
    
    while True:
        try:
            df = fetch_data(count=80)
            if df is not None and len(df) > 0:
                cur_candle_time = df['datetime'].iloc[-1]
                
                # Status heart-beat on new completed candle
                if cur_candle_time != last_candle_time:
                    last_candle_time = cur_candle_time
                    c1 = df['close'].iloc[-2]
                    ema50 = df['ema_50'].iloc[-2]
                    ema200 = df['ema_200'].iloc[-2]
                    trend = "BULLISH" if ema50 > ema200 else "BEARISH"
                    atr_val = df['atr'].iloc[-2]
                    
                    # Print status
                    account = mt5.account_info()
                    symbol_info = mt5.symbol_info(SYMBOL)
                    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Bar {df['datetime'].iloc[-2]} | "
                          f"Price: {c1:.2f} | Trend: {trend} | ATR: {atr_val:.2f} | Spread: {symbol_info.spread} pts | "
                          f"Balance: ${account.balance:,.2f} (Eq: ${account.equity:,.2f})")
                    
                    has_open = manage_open_positions(df)
                    if not has_open:
                        check_breakout_entry(df)
                        
            time.sleep(CHECK_INTERVAL_SECONDS)
            
        except KeyboardInterrupt:
            logging.info("\nBot stopped by user. Shutting down connection...")
            break
        except Exception as e:
            logging.error(f"Unexpected error: {e}", exc_info=True)
            time.sleep(30)
            
    mt5.shutdown()
    logging.info("MetaTrader 5 connection closed cleanly.")

if __name__ == "__main__":
    run_bot()
