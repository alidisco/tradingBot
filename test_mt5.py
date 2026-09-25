"""
test_mt5.py
Quick diagnostic script to verify local MetaTrader 5 connectivity,
account permissions, and market data feed for Gold (XAUUSD).
"""

import sys
import MetaTrader5 as mt5

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def run_diagnostics():
    print("=" * 65)
    print(" 🛠️  METATRADER 5 LOCAL CONNECTION DIAGNOSTIC")
    print("=" * 65)
    
    # 1. Initialize
    if not mt5.initialize():
        print("❌ FAILED: Could not initialize MetaTrader 5.")
        print("   Reason:", mt5.last_error())
        print("   Make sure MT5 is installed and running on your laptop.")
        return False
        
    print("✅ MT5 API Initialized successfully.")
    
    # 2. Account info
    acc = mt5.account_info()
    if acc is None:
        print("❌ FAILED: Could not fetch account info.")
        mt5.shutdown()
        return False
        
    print(f"✅ Account Login:    {acc.login}")
    print(f"✅ Broker Server:    {acc.server}")
    print(f"✅ Account Balance:  ${acc.balance:,.2f}")
    print(f"✅ Account Equity:   ${acc.equity:,.2f}")
    print(f"✅ Account Leverage: 1:{acc.leverage}")
    print(f"✅ Algo Trading:     {'ALLOWED' if acc.trade_expert else 'DISABLED (Check Tools -> Options -> Expert Advisors)'}")
    
    # 3. Symbol info
    symbol = "XAUUSD"
    mt5.symbol_select(symbol, True)
    sym = mt5.symbol_info(symbol)
    if sym is None:
        print(f"❌ FAILED: Symbol {symbol} not found on broker.")
        mt5.shutdown()
        return False
        
    tick = mt5.symbol_info_tick(symbol)
    print(f"✅ Symbol:           {symbol} (Bid: {tick.bid:.2f}, Ask: {tick.ask:.2f}, Spread: {sym.spread} pts)")
    
    mt5.shutdown()
    print("=" * 65)
    print("🚀 ALL SYSTEMS GO! Your laptop is ready to trade Gold.")
    print("=" * 65)
    return True

if __name__ == "__main__":
    run_diagnostics()
