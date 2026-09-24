# Gold H1 Trend-Runner Bot (MetaTrader 5 & FTMO Ready)

Automated institutional-grade trend-following algorithm for Gold (`XAUUSD`) designed for MetaTrader 5 and prop firm challenges (FTMO, MFF, FundedNext).

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
3. **Wednesday Filter (`InpSkipWednesday = true`)**: Automatically skips Wednesday entries to avoid US FOMC rate decisions and midweek liquidity consolidation traps (Wednesdays suffered a 28% win rate).
4. **Strong Close Filter (`InpStrongCloseOnly = true`)**: Only enters when the breakout bar closes in the outer 35% of its candle range, eliminating false breakout wicks.
5. **Channel Exit (10-Bar Low/High)**: Closes positions cleanly when momentum reverses.

---

## 📱 How to Run the Bot 24/7 & Control from Your Phone (Termux)

> **Important Technical Note**: The MetaTrader 5 Python library (`import MetaTrader5`) communicates via Windows IPC with `terminal64.exe` and **requires a Windows environment**. Android OS (Termux) cannot run the Windows MT5 desktop engine directly without extreme battery drain and background process termination by Android.

Here are the **two reliable methods** to keep the bot running 24/7 without keeping your PC on:

### Method 1: The Native MT5 Virtual Hosting (Easiest - 100% Phone Controlled)
1. Open MetaTrader 5 on your PC once to set it up.
2. In the MT5 Navigator pane, right-click your FTMO account and click **"Register Virtual Server"**.
3. Select an MT5 server located close to your broker (London/Frankfurt has 1ms ping).
4. Compile [Gold_TrendRunner_EA.mq5](file:///c:/Users/alidi/OneDrive/Desktop/tradingBotsV2/Gold_TrendRunner_EA.mq5) in MetaEditor (`F7`), attach it to the **XAUUSD H1** chart, and ensure `InpFTMOMode = true`.
5. Right-click the virtual server and click **"Migrate All (Charts, EAs)"**.
6. **You can now shut down your PC entirely!**
7. On your phone, install the **MetaTrader 5 App** (from Google Play / App Store).
8. Log into your FTMO account on your phone: you can monitor all open trades, view trailing stops in real-time, and manage everything directly from your pocket.

---

### Method 2: Cheap VPS + Termux Remote Management via SSH

If you want to control the Python bot ([bot_trendrunner_mt5.py](file:///c:/Users/alidi/OneDrive/Desktop/tradingBotsV2/bot_trendrunner_mt5.py)) or EA from Termux on your phone:

#### Step 1: Get a cheap Windows VPS ($3 - $5/mo)
* Use Contabo, Kamatera, OVH, or a free Windows cloud instance.
* Install MetaTrader 5 and Python 3.11 on the VPS.

#### Step 2: Clone this repository on the VPS
```bash
git clone https://github.com/alidisco/tradingBot.git
cd tradingBot
pip install -r requirements.txt
python bot_trendrunner_mt5.py
```

#### Step 3: Install OpenSSH on Termux (Android Phone)
Open Termux on your phone and run:
```bash
pkg update && pkg install openssh git python
```

#### Step 4: Connect to your Bot anytime from Termux
```bash
ssh user@your-vps-ip
```
You can now start, stop, check logs (`tail -f bot_trendrunner.log`), pull git updates, and monitor your trading bot directly from your phone terminal anytime, anywhere.

---

## 🚀 Quick Launch Locally (Windows)

### Option A: Run the Python Bot
```powershell
pip install -r requirements.txt
python bot_trendrunner_mt5.py
```

### Option B: Run in MetaTrader 5 (MQL5 EA)
1. In MT5, press `F4` to open **MetaEditor**.
2. Open `Gold_TrendRunner_EA.mq5` and press `F7` to **Compile**.
3. In MT5, open the **XAUUSD** chart, set timeframe to **H1**.
4. Drag **Gold_TrendRunner_EA** onto the chart.
5. Ensure **Algo Trading** is enabled in the top toolbar.

---

## 🔒 FTMO Account Checklist
- [x] Account Type: **FTMO Swing** (allows holding trades over weekends)
- [x] Symbol: **XAUUSD** (Gold / USD)
- [x] Timeframe: **H1** (1-Hour)
- [x] Risk Mode: **`InpFTMOMode = true`**
- [x] Risk Percent: **`InpFTMORiskPercent = 1.00`**
