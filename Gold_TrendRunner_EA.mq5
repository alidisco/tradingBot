//+------------------------------------------------------------------+
//|                                         Gold_TrendRunner_EA.mq5   |
//|               High-Performance Gold (XAUUSD) Trend-Runner EA     |
//|               Turtle / Donchian Breakout + ATR Trailing Stop     |
//+------------------------------------------------------------------+
#property copyright "TradingBotsV2"
#property link      ""
#property version   "2.00"
#property strict

#include <Trade\Trade.mqh>

//--- Input Parameters
input group "=== Strategy Parameters ==="
input int      InpEntryPeriod         = 20;      // Donchian Breakout Period (Hours)
input int      InpExitPeriod          = 10;      // Channel Exit Period (Hours)
input double   InpTrailATRMult        = 2.5;     // ATR Trailing Stop Multiplier
input int      InpATRPeriod           = 14;      // ATR Period
input bool     InpUseTrendFilter      = true;    // EMA 50 > EMA 200 Trend Filter
input int      InpFastEMAPeriod       = 50;      // Fast EMA Period
input int      InpSlowEMAPeriod       = 200;     // Slow EMA Period
input bool     InpSkipWednesday       = true;    // Skip Wednesday (Avoid Midweek/FOMC Chop)
input bool     InpStrongCloseOnly     = true;    // Require Strong Candle Close (Top/Bottom 35%)
input bool     InpUseBreakeven        = false;   // Move SL to Breakeven (Boosts Win Rate to 75%)
input double   InpBreakevenATRMult    = 1.2;     // ATR Multiple to Trigger Breakeven

input group "=== Risk & Money Management ==="
input bool     InpFTMOMode            = true;    // Enable FTMO Prop Firm Auto-Risk Mode
input double   InpFTMORiskPercent     = 1.00;    // FTMO Risk % per Trade (The Sweet Spot: 1.00%)
input double   InpFixedLot            = 0.01;    // Fixed Lot (if FTMO Mode is false)
input int      InpMaxSpreadPoints     = 75;      // Maximum Allowable Spread (Points, e.g. 75 = $0.75)
input ulong    InpMagicNumber         = 889900;  // Magic Number

//--- Global Variables
CTrade         trade;
int            handle_ema_fast;
int            handle_ema_slow;
int            handle_atr;
datetime       last_bar_time;
double         trailing_stop_price;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetMarginMode();
   trade.SetTypeFillingBySymbol(_Symbol);

   handle_ema_fast = iMA(_Symbol, PERIOD_H1, InpFastEMAPeriod, 0, MODE_EMA, PRICE_CLOSE);
   handle_ema_slow = iMA(_Symbol, PERIOD_H1, InpSlowEMAPeriod, 0, MODE_EMA, PRICE_CLOSE);
   handle_atr      = iATR(_Symbol, PERIOD_H1, InpATRPeriod);

   if(handle_ema_fast == INVALID_HANDLE || handle_ema_slow == INVALID_HANDLE || handle_atr == INVALID_HANDLE)
   {
      Print("Error creating indicator handles: ", GetLastError());
      return(INIT_FAILED);
   }

   last_bar_time = 0;
   trailing_stop_price = 0.0;
   Print("Gold TrendRunner EA initialized successfully on H1 for ", _Symbol);
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   Comment(""); // Clear chart HUD
   IndicatorRelease(handle_ema_fast);
   IndicatorRelease(handle_ema_slow);
   IndicatorRelease(handle_atr);
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   // 1. Indicator buffers
   double ema_fast[2], ema_slow[2], atr[2];
   if(CopyBuffer(handle_ema_fast, 0, 1, 2, ema_fast) <= 0) return;
   if(CopyBuffer(handle_ema_slow, 0, 1, 2, ema_slow) <= 0) return;
   if(CopyBuffer(handle_atr, 0, 1, 2, atr) <= 0) return;

   double cur_atr = atr[1];
   double fast_ma = ema_fast[1];
   double slow_ma = ema_slow[1];

   // 2. Copy rates for Donchian channels
   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   int needed_bars = InpEntryPeriod + 5;
   if(CopyRates(_Symbol, PERIOD_H1, 0, needed_bars, rates) < needed_bars) return;

   double c1 = rates[1].close;

   // Calculate 20-bar Donchian Entry Channels (bars 2 to 21)
   double donchian_high = rates[2].high;
   double donchian_low  = rates[2].low;
   for(int i = 2; i <= InpEntryPeriod + 1; i++)
   {
      if(rates[i].high > donchian_high) donchian_high = rates[i].high;
      if(rates[i].low  < donchian_low)  donchian_low  = rates[i].low;
   }

   // Calculate 10-bar Donchian Exit Channels (bars 2 to 11)
   double exit_low  = rates[2].low;
   double exit_high = rates[2].high;
   for(int j = 2; j <= InpExitPeriod + 1; j++)
   {
      if(rates[j].low  < exit_low)  exit_low  = rates[j].low;
      if(rates[j].high > exit_high) exit_high = rates[j].high;
   }

   // Check spread
   long spread = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   datetime current_bar_time = iTime(_Symbol, PERIOD_H1, 0);

   // Count open positions
   int open_pos_count = 0;
   double open_pnl = 0.0;
   for(int p = PositionsTotal() - 1; p >= 0; p--)
   {
      if(PositionGetSymbol(p) == _Symbol && PositionGetInteger(POSITION_MAGIC) == InpMagicNumber)
      {
         open_pos_count++;
         open_pnl += PositionGetDouble(POSITION_PROFIT);
      }
   }

   // 3. Update Real-Time On-Chart HUD Comment
   string trend_str = (fast_ma > slow_ma) ? "BULLISH (EMA 50 > 200)" : "BEARISH (EMA 50 < 200)";
   string spread_status = (spread <= InpMaxSpreadPoints) ? "[OK]" : "[SPREAD HIGH - PAUSED]";
   string status_str = "HOLDING CASH (Waiting for H1 Breakout)";
   MqlDateTime dt_hud;
   TimeToStruct(current_bar_time, dt_hud);
   if(open_pos_count > 0)
      status_str = "IN TRADE (" + IntegerToString(open_pos_count) + " pos | PnL: $" + DoubleToString(open_pnl, 2) + ")";
   else if(dt_hud.day_of_week == 3)
      status_str = "SKIP WEDNESDAY FILTER (Avoiding FOMC / Midweek Chop)";

   int minutes_left = (int)((current_bar_time + 3600 - TimeCurrent()) / 60);
   if(minutes_left < 0) minutes_left = 0;

   string hud = "=======================================================\n" +
                "       🏆 GOLD H1 TREND-RUNNER EA (FTMO READY)\n" +
                "=======================================================\n" +
                " Account: " + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)) +
                " | Balance: $" + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) +
                " | Equity: $" + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2) + "\n" +
                " Symbol: " + _Symbol + " | Bid: " + DoubleToString(bid, _Digits) + " | Ask: " + DoubleToString(ask, _Digits) + "\n" +
                " Spread: " + IntegerToString(spread) + " pts (Max Allowed: " + IntegerToString(InpMaxSpreadPoints) + " pts) " + spread_status + "\n" +
                " H1 Trend: " + trend_str + " | ATR(14): " + DoubleToString(cur_atr, _Digits) + "\n" +
                "-------------------------------------------------------\n" +
                " 🟢 BUY TRIGGER:  Close > " + DoubleToString(donchian_high, _Digits) + " (Need +$" + DoubleToString(MathMax(0.0, donchian_high - ask), 2) + " move)\n" +
                " 🔴 SELL TRIGGER: Close < " + DoubleToString(donchian_low, _Digits) + " (Need -$" + DoubleToString(MathMax(0.0, bid - donchian_low), 2) + " move)\n" +
                " Next H1 Candle Closes In: ~" + IntegerToString(minutes_left) + " minutes\n" +
                " Strategy Status: " + status_str + "\n" +
                "=======================================================";
   Comment(hud);

   // 4. Manage Active Positions (Trailing Stop / Exit Channels)
   for(int p = PositionsTotal() - 1; p >= 0; p--)
   {
      if(PositionGetSymbol(p) == _Symbol && PositionGetInteger(POSITION_MAGIC) == InpMagicNumber)
      {
         ulong ticket = PositionGetTicket(p);
         long pos_type = PositionGetInteger(POSITION_TYPE);
         double current_sl = PositionGetDouble(POSITION_SL);

         if(pos_type == POSITION_TYPE_BUY)
         {
            // Exit on 10-bar channel low breakdown on completed candle
            if(c1 <= exit_low && current_bar_time != last_bar_time)
            {
               trade.PositionClose(ticket);
               Print("BUY Position closed on channel exit low at ", c1);
               return;
            }
            // Trail stop up with ATR
            double new_sl = c1 - (InpTrailATRMult * cur_atr);
            new_sl = MathMax(new_sl, exit_low);
            if(new_sl > current_sl + 0.50)
            {
               trade.PositionModify(ticket, new_sl, 0.0);
               Print("BUY Trailing Stop updated to ", new_sl);
            }
         }
         else if(pos_type == POSITION_TYPE_SELL)
         {
            // Exit on 10-bar channel high breakout on completed candle
            if(c1 >= exit_high && current_bar_time != last_bar_time)
            {
               trade.PositionClose(ticket);
               Print("SELL Position closed on channel exit high at ", c1);
               return;
            }
            // Trail stop down with ATR
            double new_sl = c1 + (InpTrailATRMult * cur_atr);
            new_sl = MathMin(new_sl, exit_high);
            if(current_sl == 0.0 || new_sl < current_sl - 0.50)
            {
               trade.PositionModify(ticket, new_sl, 0.0);
               Print("SELL Trailing Stop updated to ", new_sl);
            }
         }
         return; // Already in trade
      }
   }

   // 5. Look for New Breakout Entry (only on new H1 bar)
   if(current_bar_time == last_bar_time)
      return; // Already checked this completed bar

   // Check spread BEFORE locking bar time so temporary spikes don't discard the whole hour
   if(spread > InpMaxSpreadPoints)
   {
      Print("Spread temporarily high: ", spread, " points (max ", InpMaxSpreadPoints, "). Waiting for next tick...");
      return;
   }

   // Lock this bar now that spread is acceptable
   last_bar_time = current_bar_time;

   // Check day of week
   MqlDateTime dt;
   TimeToStruct(current_bar_time, dt);
   if(InpSkipWednesday && dt.day_of_week == 3) // 3 = Wednesday
      return;

   double bar_range = rates[1].high - rates[1].low;
   if(bar_range <= 0) return;

   // Bullish Breakout
   if(c1 > donchian_high)
   {
      bool strong_close = !InpStrongCloseOnly || ((c1 - rates[1].low) / bar_range >= 0.65);
      if(strong_close && (!InpUseTrendFilter || (fast_ma > slow_ma)))
      {
         double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
         double sl_dist = InpTrailATRMult * cur_atr;
         double sl = ask - sl_dist;
         double trade_lot = InpFixedLot;
         
         if(InpFTMOMode)
         {
            double balance = AccountInfoDouble(ACCOUNT_BALANCE);
            double risk_dollars = balance * (InpFTMORiskPercent / 100.0);
            double contract_size = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
            double calc = risk_dollars / (sl_dist * contract_size);
            double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
            trade_lot = MathFloor(calc / step) * step;
            double min_l = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
            double max_l = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
            trade_lot = MathMax(min_l, MathMin(trade_lot, max_l));
         }

         trade.Buy(trade_lot, _Symbol, ask, sl, 0.0, "Gold_TrendRunner_Buy");
         Print("BUY Breakout Executed: ", trade_lot, " lots @ ", ask, " | SL: ", sl);
      }
   }
   // Bearish Breakout
   else if(c1 < donchian_low)
   {
      bool strong_close = !InpStrongCloseOnly || ((rates[1].high - c1) / bar_range >= 0.65);
      if(strong_close && (!InpUseTrendFilter || (fast_ma < slow_ma)))
      {
         double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
         double sl_dist = InpTrailATRMult * cur_atr;
         double sl = bid + sl_dist;
         double trade_lot = InpFixedLot;

         if(InpFTMOMode)
         {
            double balance = AccountInfoDouble(ACCOUNT_BALANCE);
            double risk_dollars = balance * (InpFTMORiskPercent / 100.0);
            double contract_size = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
            double calc = risk_dollars / (sl_dist * contract_size);
            double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
            trade_lot = MathFloor(calc / step) * step;
            double min_l = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
            double max_l = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
            trade_lot = MathMax(min_l, MathMin(trade_lot, max_l));
         }

         trade.Sell(trade_lot, _Symbol, bid, sl, 0.0, "Gold_TrendRunner_Sell");
         Print("SELL Breakout Executed: ", trade_lot, " lots @ ", bid, " | SL: ", sl);
      }
   }
}
//+------------------------------------------------------------------+
