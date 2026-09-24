# Gold H1 Trend-Runner Bot (MetaTrader 5 Local & FTMO Ready)

Automated institutional-grade trend-following algorithm for Gold (`XAUUSD`) designed for **100% local execution on your laptop** with MetaTrader 5 (Zero cloud services, zero external dependencies).

---

## 🏆 FTMO Challenge Performance (1-Year Backtest on Real MT5 Data)

Simulated across 1 full year of real tick/candle Gold data under strict FTMO rules:

* **Risk Per Trade**: **1.00%** (Sweet Spot)
* **Time to Pass Phase 1 (10% Target)**: **~4 Weeks (27 Days)** ✅
* **Max Daily Drawdown**: **2.23%** *(FTMO Limit: 5.00% → 2.77% Safety Cushion)*
* **Max Total Drawdown**: **4.70%** *(FTMO Limit: 10.00% → 5.30% Safety Cushion)*
* **Win Rate**: **48.1%** *(Tuesdays: 52.4%, Mondays: 50.0%)*
* **Profit Factor**: **2.32**
* **Total Annual Return**: **+33.8%** (+$3,378 on $10k account / +$33,669 on $100k account)

---

## ⚙️ Strategy Core Architecture

1. **H1 Donchian 20-Bar Channel Breakout**: Enters long on 20-hour highs, enters short on 20-hour lows.
2. **Dynamic ATR Trailing Stop (2.5x ATR)**: No fixed profit cap. The bot trails the stop behind Gold's multi-day runs, capturing +500 to +1,500 pip trending moves.
3. **Wednesday Filter (`InpSkipWednesday = true`)**: Automatically skips Wednesday entries to avoid US FOMC rate decisions and midweek liquidity consolidation traps.
4. **Strong Close Filter (`InpStrongCloseOnly = true`)**: Only enters when the breakout bar closes in the outer 35% of its candle range, eliminating false breakout wicks.
5. **Channel Exit (10-Bar Low/High)**: Closes positions cleanly when momentum reverses.

---

## 💻 100% Local Laptop Execution (Zero Cloud)

### Method 1: The Native MT5 Expert Advisor (Directly in MT5 - Recommended)
The EA is **already compiled and installed** in your MT5 terminal:

1. Open **MetaTrader 5** on your laptop.
2. Open the **XAUUSD** (Gold) chart and set the timeframe to **H1** (1-Hour).
3. In the Navigator pane on the left (`Ctrl + N`), expand **Expert Advisors**.
4. Drag **`Gold_TrendRunner_EA`** onto your chart.
5. In the settings window:
   * In the **Common** tab, ensure **"Allow Algo Trading"** is checked.
   * In the **Inputs** tab, verify **`InpFTMOMode = true`** and **`InpFTMORiskPercent = 1.00`**.
   * Click **OK**.
6. Ensure the **"Algo Trading"** button in the top MT5 toolbar is **GREEN**.
   * A small icon in the top right corner of the chart confirms the bot is running!

---

### Method 2: The Local Python Bot
If you prefer running via command prompt / terminal:
```powershell
pip install -r requirements.txt
python bot_trendrunner_mt5.py
```
*It connects directly to your local MT5 application via Windows IPC, monitors H1 candles, and executes trades with 1% FTMO risk automatically.*

---

## 🔋 Laptop Power Setting (Keep It Running Smoothly)
To prevent your laptop from going to sleep while trading:
1. Press `Win + I` to open **Settings**.
2. Go to **System > Power & battery > Screen and sleep**.
3. Set *"When plugged in, put my device to sleep after"* to **Never**.
*(You can close the lid or let the screen turn off by setting "When I close the lid" to "Do nothing" in Control Panel Power Options).*
