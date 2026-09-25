"""
simulate_ftmo_live.py
Fetches 1 year of real historical H1 data from MT5 for XAUUSD and runs
a comprehensive simulation of the exact bot in main.py against FTMO Challenge rules.
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import sys
from datetime import datetime, timedelta

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def fetch_historical_h1(days=365):
    if not mt5.initialize():
        print("MT5 init failed:", mt5.last_error())
        return None
        
    mt5.symbol_select("XAUUSD", True)
    now = datetime.now()
    start_date = now - timedelta(days=days)
    
    print(f"Fetching XAUUSD H1 rates from {start_date.strftime('%Y-%m-%d')} to {now.strftime('%Y-%m-%d')}...")
    rates = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_H1, start_date, now)
    mt5.shutdown()
    
    if rates is None or len(rates) == 0:
        print("No rates returned from MT5.")
        return None
        
    df = pd.DataFrame(rates)
    df['datetime'] = pd.to_datetime(df['time'], unit='s')
    df.sort_values(by='time', inplace=True)
    df.reset_index(drop=True, inplace=True)
    print(f"Loaded {len(df)} H1 bars from {df['datetime'].iloc[0]} to {df['datetime'].iloc[-1]}.")
    return df

def simulate_ftmo(df, start_index=50, account_size=10000.0, risk_pct=0.01, phase=1, use_trend_filter=True, stop_on_pass=True):
    target_pct = 0.10 if phase == 1 else 0.05
    target_profit = account_size * target_pct
    target_balance = account_size + target_profit
    
    df = df.copy()
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    hl = df['high'] - df['low']
    hc = (df['high'] - df['close'].shift()).abs()
    lc = (df['low'] - df['close'].shift()).abs()
    df['atr'] = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(14).mean()
    
    ENTRY_PERIOD = 20
    EXIT_PERIOD = 10
    TRAIL_ATR_MULT = 2.5
    
    df['entry_high'] = df['high'].rolling(ENTRY_PERIOD).max().shift(1)
    df['entry_low'] = df['low'].rolling(ENTRY_PERIOD).min().shift(1)
    df['exit_low'] = df['low'].rolling(EXIT_PERIOD).min().shift(1)
    df['exit_high'] = df['high'].rolling(EXIT_PERIOD).max().shift(1)
    
    c = df['close'].values
    o = df['open'].values
    h = df['high'].values
    l = df['low'].values
    atr = df['atr'].values
    ema50 = df['ema_50'].values
    ema200 = df['ema_200'].values
    eh = df['entry_high'].values
    el = df['entry_low'].values
    xl = df['exit_low'].values
    xh = df['exit_high'].values
    times = df['datetime'].values
    
    balance = account_size
    peak_equity = account_size
    lowest_equity = account_size
    
    max_daily_dd_pct = 0.0
    max_overall_dd_pct = 0.0
    
    current_day = None
    day_start_balance = balance
    day_worst_equity = balance
    
    in_pos = False
    pdir = 0
    entry_p, sl_p, lot = 0, 0, 0
    contract_size = 100.0
    spread = 0.35
    
    passed = False
    pass_date = None
    pass_trade_count = 0
    violated_daily = False
    violated_total = False
    
    trades = []
    start_sim_time = times[start_index]
    
    for i in range(start_index, len(df)):
        cur_time = times[i]
        cur_date = pd.Timestamp(cur_time).date()
        cur_atr = atr[i]
        
        # New Day Reset for FTMO Daily Drawdown Limit
        if cur_date != current_day:
            current_day = cur_date
            day_start_balance = balance
            day_worst_equity = balance
            
        # Manage open trade
        if in_pos:
            if pdir == 1:
                floating_low = (l[i] - entry_p) * lot * contract_size
                equity_low = balance + floating_low
                if equity_low < day_worst_equity:
                    day_worst_equity = equity_low
                if equity_low < lowest_equity:
                    lowest_equity = equity_low
                    
                daily_loss_pct = ((day_start_balance - day_worst_equity) / day_start_balance) * 100.0
                if daily_loss_pct > max_daily_dd_pct:
                    max_daily_dd_pct = daily_loss_pct
                if daily_loss_pct >= 5.0:
                    violated_daily = True
                    break
                    
                overall_dd_pct = ((peak_equity - equity_low) / account_size) * 100.0
                if overall_dd_pct > max_overall_dd_pct:
                    max_overall_dd_pct = overall_dd_pct
                if equity_low <= (account_size * 0.90): # 10% max total loss
                    violated_total = True
                    break
                    
                # Check exit on 10-bar low or trailing stop
                current_stop = max(sl_p, xl[i])
                if l[i] <= current_stop:
                    exit_p = current_stop
                    pnl = (exit_p - entry_p) * lot * contract_size
                    balance += pnl
                    trades.append({
                        'pnl': pnl, 'type': 'BUY', 'entry_date': str(entry_date), 'exit_date': str(cur_date),
                        'pips': (exit_p - entry_p) / 0.10, 'balance_after': balance
                    })
                    in_pos = False
                else:
                    sl_p = max(sl_p, c[i] - (TRAIL_ATR_MULT * cur_atr))
                    
            elif pdir == -1:
                floating_high = (entry_p - h[i]) * lot * contract_size
                equity_low = balance + floating_high
                if equity_low < day_worst_equity:
                    day_worst_equity = equity_low
                if equity_low < lowest_equity:
                    lowest_equity = equity_low
                    
                daily_loss_pct = ((day_start_balance - day_worst_equity) / day_start_balance) * 100.0
                if daily_loss_pct > max_daily_dd_pct:
                    max_daily_dd_pct = daily_loss_pct
                if daily_loss_pct >= 5.0:
                    violated_daily = True
                    break
                    
                overall_dd_pct = ((peak_equity - equity_low) / account_size) * 100.0
                if overall_dd_pct > max_overall_dd_pct:
                    max_overall_dd_pct = overall_dd_pct
                if equity_low <= (account_size * 0.90):
                    violated_total = True
                    break
                    
                current_stop = min(sl_p, xh[i])
                if h[i] >= current_stop:
                    exit_p = current_stop
                    pnl = (entry_p - exit_p) * lot * contract_size
                    balance += pnl
                    trades.append({
                        'pnl': pnl, 'type': 'SELL', 'entry_date': str(entry_date), 'exit_date': str(cur_date),
                        'pips': (entry_p - exit_p) / 0.10, 'balance_after': balance
                    })
                    in_pos = False
                else:
                    sl_p = min(sl_p, c[i] + (TRAIL_ATR_MULT * cur_atr))
                    
            if balance > peak_equity:
                peak_equity = balance
                
            # Check target reached
            if balance >= target_balance and not passed:
                passed = True
                pass_date = str(cur_date)
                pass_trade_count = len(trades)
                if stop_on_pass:
                    break
                
            continue
            
        # Entry checks (exact logic in main.py)
        # Skip Wednesday (day 2)
        if pd.Timestamp(cur_time).weekday() == 2:
            continue
            
        bar_range = h[i] - l[i]
        if bar_range <= 0 or np.isnan(cur_atr):
            continue
            
        # 1.00% Risk lot calculation
        risk_dollars = balance * risk_pct
        sl_dist = TRAIL_ATR_MULT * cur_atr
        calc_lot = risk_dollars / (sl_dist * contract_size)
        calc_lot = round(round(calc_lot / 0.01) * 0.01, 2)
        calc_lot = max(0.01, min(calc_lot, 10.0))
        
        # Bullish Breakout
        trend_ok_buy = (not use_trend_filter) or (ema50[i] > ema200[i])
        trend_ok_sell = (not use_trend_filter) or (ema50[i] < ema200[i])
        
        if c[i] > eh[i] and trend_ok_buy:
            if (c[i] - l[i]) / bar_range >= 0.65: # Strong close
                entry_p = c[i] + spread
                sl_p = entry_p - sl_dist
                lot = calc_lot
                pdir = 1
                in_pos = True
                entry_date = cur_date
                
        # Bearish Breakout
        elif c[i] < el[i] and trend_ok_sell:
            if (h[i] - c[i]) / bar_range >= 0.65: # Strong close
                entry_p = c[i]
                sl_p = entry_p + sl_dist
                lot = calc_lot
                pdir = -1
                in_pos = True
                entry_date = cur_date

    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] < 0]
    total_pips = sum(t['pips'] for t in trades)
    wr = (len(wins) / len(trades) * 100.0) if trades else 0.0
    
    days_to_pass = (pd.Timestamp(pass_date).date() - pd.Timestamp(start_sim_time).date()).days if passed else None
    
    return {
        'account_size': account_size,
        'phase': phase,
        'target_pct': target_pct * 100,
        'passed': passed,
        'pass_date': pass_date,
        'days_to_pass': days_to_pass,
        'trades_to_pass': pass_trade_count if passed else len(trades),
        'final_balance': round(balance, 2),
        'net_profit': round(balance - account_size, 2),
        'lowest_equity': round(lowest_equity, 2),
        'peak_equity': round(peak_equity, 2),
        'max_daily_dd_pct': round(max_daily_dd_pct, 2),
        'max_overall_dd_pct': round(max_overall_dd_pct, 2),
        'violated_daily': violated_daily,
        'violated_total': violated_total,
        'total_trades': len(trades),
        'wins': len(wins),
        'losses': len(losses),
        'win_rate': round(wr, 1),
        'total_pips': round(total_pips, 1),
        'trades': trades
    }

if __name__ == "__main__":
    df = fetch_historical_h1(days=365)
    if df is not None:
        print("\n" + "=" * 80)
        print(" 🎯 SIMULATION 1: FTMO CHALLENGE PHASE 1 (+10% TARGET, 1.00% RISK)")
        print("    (Mode: Strict FTMO - Stop trading immediately when target is achieved)")
        print("=" * 80)
        for acc in [10000.0, 25000.0, 50000.0, 100000.0]:
            res = simulate_ftmo(df, start_index=50, account_size=acc, risk_pct=0.01, phase=1, use_trend_filter=True, stop_on_pass=True)
            status = "✅ PASSED" if (res['passed'] and not res['violated_daily'] and not res['violated_total']) else "❌ FAILED"
            print(f"Account: ${int(acc):<7} | Target: +${int(acc*0.10):<5} | Status: {status} on {res['pass_date']} "
                  f"({res['days_to_pass']} days / {res['trades_to_pass']} trades)")
            print(f"   Max Daily DD During Challenge: {res['max_daily_dd_pct']:>4.2f}% (Limit: 5.00% | Safety Buffer: {5.0 - res['max_daily_dd_pct']:>4.2f}%)")
            print(f"   Max Total DD During Challenge: {res['max_overall_dd_pct']:>4.2f}% (Limit: 10.00% | Safety Buffer: {10.0 - res['max_overall_dd_pct']:>4.2f}%)")
            if acc == 10000.0:
                print("   Detailed Trade Progression ($10,000 Account):")
                for tidx, t in enumerate(res['trades']):
                    print(f"      Trade #{tidx+1:<2}: {t['type']:<4} | {t['entry_date']} -> {t['exit_date']} | "
                          f"Pips: {t['pips']:>6.1f} | PnL: ${t['pnl']:>7.2f} | Balance: ${t['balance_after']:>9.2f}")
                print()

        print("=" * 80)
        print(" 🎯 SIMULATION 2: FTMO CHALLENGE PHASE 2 (+5% TARGET, 1.00% RISK)")
        print("=" * 80)
        res_p2 = simulate_ftmo(df, start_index=50, account_size=10000.0, risk_pct=0.01, phase=2, use_trend_filter=True, stop_on_pass=True)
        status_p2 = "✅ PASSED" if (res_p2['passed'] and not res_p2['violated_daily'] and not res_p2['violated_total']) else "❌ FAILED"
        print(f"Phase 2 ($10,000 Acc) | Target: +$500 (5%) | Status: {status_p2} on {res_p2['pass_date']} ({res_p2['days_to_pass']} days / {res_p2['trades_to_pass']} trades)")
        print(f"   Max Daily DD: {res_p2['max_daily_dd_pct']:>4.2f}% (Limit 5.0%) | Max Total DD: {res_p2['max_overall_dd_pct']:>4.2f}% (Limit 10.0%)\n")

        print("=" * 80)
        print(" 🎯 SIMULATION 3: ROLLING START DATES (What if you start in different months?)")
        print("=" * 80)
        # Sample start dates across different months in the dataset
        sample_indices = []
        months_seen = set()
        for idx in range(50, len(df)-200, 24*15): # check every 15 days
            month_key = df['datetime'].iloc[idx].strftime('%Y-%m')
            if month_key not in months_seen:
                months_seen.add(month_key)
                sample_indices.append(idx)

        print(f"{'Start Month':<12} | {'Start Date':<12} | {'Result':<10} | {'Days':<6} | {'Trades':<8} | {'Max Daily DD':<14} | {'Max Total DD':<14}")
        print("-" * 86)
        
        pass_count = 0
        total_cohorts = 0
        for s_idx in sample_indices:
            s_date = df['datetime'].iloc[s_idx].strftime('%Y-%m-%d')
            m_label = df['datetime'].iloc[s_idx].strftime('%b %Y')
            r = simulate_ftmo(df, start_index=s_idx, account_size=10000.0, risk_pct=0.01, phase=1, use_trend_filter=True, stop_on_pass=True)
            total_cohorts += 1
            if r['passed'] and not r['violated_daily'] and not r['violated_total']:
                pass_count += 1
                res_str = "PASS"
                days_str = f"{r['days_to_pass']}d"
            elif r['violated_daily']:
                res_str = "FAIL (Daily)"
                days_str = "N/A"
            elif r['violated_total']:
                res_str = "FAIL (Total)"
                days_str = "N/A"
            else:
                res_str = "IN PROGRESS"
                days_str = ">30d"
                
            print(f"{m_label:<12} | {s_date:<12} | {res_str:<10} | {days_str:<6} | {r['trades_to_pass']:<8} | {r['max_daily_dd_pct']:>5.2f}%         | {r['max_overall_dd_pct']:>5.2f}%")

        print("-" * 86)
        print(f"Overall Passing Rate across different start dates: {pass_count}/{total_cohorts} ({pass_count/total_cohorts*100:.1f}%)")
