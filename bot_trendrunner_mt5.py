"""
bot_trendrunner_mt5.py
Live MetaTrader 5 Python Trading Bot for Gold (XAUUSD)
Implements the High-Performance H1 Donchian Breakout + ATR Trailing Stop Strategy.
"""

import time
import logging
import MetaTrader5 as mt5
import pandas as pd
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("bot_trendrunner.log"),
        logging.StreamHandler()
    ]
)

SYMBOL = "XAUUSD"
TIMEFRAME = mt5.TIMEFRAME_H1
MAGIC_NUMBER = 889900
FIXED_LOT = 0.01
FTMO_MODE = True           # Auto-calculate exact lot size for FTMO
FTMO_RISK_PERCENT = 1.00   # 1.00% Risk per trade (The Sweet Spot)
ENTRY_PERIOD = 20
EXIT_PERIOD = 10
ATR_PERIOD = 14
TRAIL_ATR_MULT = 2.5
MAX_SPREAD_POINTS = 75
CHECK_INTERVAL_SECONDS = 30

def initialize_mt5():
    if not mt5.initialize():
        logging.error(f"MT5 initialize failed: {mt5.last_error()}")
        return False
        
    symbol_info = mt5.symbol_info(SYMBOL)
    if not symbol_info:
        logging.error(f"Symbol {SYMBOL} not found.")
        mt5.shutdown()
        return False
        
    mt5.symbol_select(SYMBOL, True)
    acc = mt5.account_info()
    logging.info(f"Connected to MT5. Account: {acc.login}, Balance: ${acc.balance:.2f}, Leverage: 1:{acc.leverage}")
    return True

def fetch_data(count=80):
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, count)
    if rates is None or len(rates) == 0:
        return None
        
    df = pd.DataFrame(rates)
    df['datetime'] = pd.to_datetime(df['time'], unit='s')
    
    # Calculate EMA 50 and 200
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # ATR
    hl = df['high'] - df['low']
    hc = (df['high'] - df['close'].shift()).abs()
    lc = (df['low'] - df['close'].shift()).abs()
    df['atr'] = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(ATR_PERIOD).mean()
    
    return df

def manage_open_positions(df):
    positions = mt5.positions_get(symbol=SYMBOL)
    if not positions:
        return False
        
    bot_positions = [p for p in positions if p.magic == MAGIC_NUMBER]
    if not bot_positions:
        return False
        
    pos = bot_positions[0]
    ticket = pos.ticket
    pos_type = pos.type
    current_sl = pos.sl
    
    # Exit channels based on completed bars
    recent_bars = df.iloc[-EXIT_PERIOD-1:-1]
    exit_low = recent_bars['low'].min()
    exit_high = recent_bars['high'].max()
    cur_atr = df['atr'].iloc[-2]
    cur_close = df['close'].iloc[-2]
    
    if pos_type == mt5.ORDER_TYPE_BUY:
        # Exit condition
        if cur_close <= exit_low:
            logging.info(f"Closing BUY trade #{ticket} on channel exit breakdown.")
            close_position(pos)
            return True
            
        # Trailing Stop update
        new_sl = max(cur_close - (TRAIL_ATR_MULT * cur_atr), exit_low)
        if new_sl > current_sl + 0.50:
            modify_sl(ticket, new_sl)
            
    elif pos_type == mt5.ORDER_TYPE_SELL:
        if cur_close >= exit_high:
            logging.info(f"Closing SELL trade #{ticket} on channel exit breakout.")
            close_position(pos)
            return True
            
        new_sl = min(cur_close + (TRAIL_ATR_MULT * cur_atr), exit_high)
        if current_sl == 0.0 or new_sl < current_sl - 0.50:
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
        "comment": "Close_TrendRunner",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC
    }
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
        logging.info(f"Trailing SL updated to {new_sl:.2f}")

def check_breakout_entry(df):
    symbol_info = mt5.symbol_info(SYMBOL)
    if symbol_info.spread > MAX_SPREAD_POINTS:
        return
        
    completed_bar = df.iloc[-2]
    c1 = completed_bar['close']
    ema50 = completed_bar['ema_50']
    ema200 = completed_bar['ema_200']
    cur_atr = completed_bar['atr']
    
    # Day of week check
    bar_time = completed_bar['datetime']
    if bar_time.weekday() == 2: # Wednesday = 2
        return
        
    bar_range = completed_bar['high'] - completed_bar['low']
    if bar_range <= 0:
        return
        
    # 20-bar Donchian Entry Channel (bars -21 to -2)
    entry_bars = df.iloc[-ENTRY_PERIOD-1:-1]
    donchian_high = entry_bars['high'].iloc[:-1].max()
    donchian_low = entry_bars['low'].iloc[:-1].min()
    
    # Bullish Breakout
    if c1 > donchian_high and ema50 > ema200:
        strong_close = (c1 - completed_bar['low']) / bar_range >= 0.65
        if strong_close:
            ask = symbol_info.ask
            sl = ask - (TRAIL_ATR_MULT * cur_atr)
            execute_entry(mt5.ORDER_TYPE_BUY, ask, sl)
        
    # Bearish Breakout
    elif c1 < donchian_low and ema50 < ema200:
        strong_close = (completed_bar['high'] - c1) / bar_range >= 0.65
        if strong_close:
            bid = symbol_info.bid
            sl = bid + (TRAIL_ATR_MULT * cur_atr)
            execute_entry(mt5.ORDER_TYPE_SELL, bid, sl)

def execute_entry(order_type, price, sl):
    symbol_info = mt5.symbol_info(SYMBOL)
    account = mt5.account_info()
    
    trade_lot = FIXED_LOT
    if FTMO_MODE and account:
        sl_dist = abs(price - sl)
        if sl_dist > 0:
            risk_dollars = account.balance * (FTMO_RISK_PERCENT / 100.0)
            contract_size = symbol_info.trade_contract_size
            calc_lot = risk_dollars / (sl_dist * contract_size)
            calc_lot = round(round(calc_lot / symbol_info.volume_step) * symbol_info.volume_step, 2)
            trade_lot = max(symbol_info.volume_min, min(calc_lot, symbol_info.volume_max))

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
        "comment": "FTMO_TrendRunner",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC
    }
    res = mt5.order_send(request)
    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
        logging.info(f"ENTRY EXECUTED: {'BUY' if order_type == 0 else 'SELL'} {trade_lot} lots @ {price:.2f} | SL: {sl:.2f} (Risk: {FTMO_RISK_PERCENT}% = ${account.balance * FTMO_RISK_PERCENT / 100:.2f})")
    else:
        logging.error(f"Entry failed: {res.comment if res else mt5.last_error()}")

def main_loop():
    logging.info("Starting Gold H1 Trend-Runner Bot...")
    last_candle_time = None
    
    while True:
        try:
            df = fetch_data(count=80)
            if df is not None and len(df) > 0:
                cur_candle_time = df['datetime'].iloc[-1]
                
                # Bar open check
                if cur_candle_time != last_candle_time:
                    last_candle_time = cur_candle_time
                    logging.info(f"New H1 candle detected at {cur_candle_time}. Analyzing trend...")
                    
                    has_open = manage_open_positions(df)
                    if not has_open:
                        check_breakout_entry(df)
                        
            time.sleep(CHECK_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            logging.info("Stopping on user interrupt.")
            break
        except Exception as e:
            logging.error(f"Error: {e}")
            time.sleep(30)
            
    mt5.shutdown()

if __name__ == "__main__":
    if initialize_mt5():
        main_loop()
