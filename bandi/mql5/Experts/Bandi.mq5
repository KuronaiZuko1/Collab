//+------------------------------------------------------------------+
//|                                                        Bandi.mq5 |
//|                                  Copyright 2026, BANDI Project   |
//|                       https://github.com/KuronaiZuko1/Collab.git |
//+------------------------------------------------------------------+
#property copyright   "BANDI Project"
#property link        "https://github.com/KuronaiZuko1/Collab.git"
#property version     "2.00"
#property description "BANDI - Local-First Automated Trading Intelligence & Execution Bridge"

#include <Trade\Trade.mqh>

//--- Input parameters
input group "=== BANDI Server Settings ==="
input string   InpServerUrl         = "http://127.0.0.1:8000/api/mt5/sync";        // Backend Sync Endpoint
input string   InpResultUrl         = "http://127.0.0.1:8000/api/mt5/orders/result"; // Result Endpoint
input int      InpSyncIntervalSec   = 3;                                           // Telemetry Interval (sec)

input group "=== Execution & Risk Parameters ==="
input ulong    InpMagicNumber       = 202611;                                      // Magic Number
input ulong    InpDeviation         = 10;                                          // Max Price Deviation (points)
input double   InpMaxLot            = 1.0;                                         // EA Hard Max Lot Limit
input int      InpMaxSpreadPoints   = 35;                                          // Max Allowed Spread (points)
input bool     InpAutoBreakeven     = true;                                        // Move SL to Breakeven at 1R

input group "=== Display ==="
input bool     InpShowOnChartPanel  = true;                                        // Show On-Chart Monitor

//--- Global variables
CTrade         m_trade;
datetime       m_last_sync_time     = 0;
string         m_latest_event_title = "Scanning upcoming releases...";
string         m_latest_event_time  = "30m Alert Guard Active";
string         m_server_trading_mode= "OFF";
bool           m_server_locked      = true;
bool           m_kill_switch_active = false;
string         m_webrequest_status  = "Initializing...";
bool           m_webrequest_ok      = false;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("BANDI v2.0: Initializing Trading Intelligence Bridge on ", _Symbol);

   m_trade.SetExpertMagicNumber(InpMagicNumber);
   m_trade.SetDeviationInPoints(InpDeviation);

   // Configure trade filling mode supported by symbol
   uint filling = (uint)SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   if((filling & SYMBOL_FILLING_FOK) != 0)
      m_trade.SetTypeFilling(ORDER_FILLING_FOK);
   else if((filling & SYMBOL_FILLING_IOC) != 0)
      m_trade.SetTypeFilling(ORDER_FILLING_IOC);
   else
      m_trade.SetTypeFilling(ORDER_FILLING_RETURN);

   EventSetTimer(1); // 1-second timer
   UpdateChartDisplay();

   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   Comment("");
   Print("BANDI: Deinitialized successfully (reason: ", reason, ")");
}

//+------------------------------------------------------------------+
//| Expert timer function                                            |
//+------------------------------------------------------------------+
void OnTimer()
{
   datetime now = TimeCurrent();

   // Periodic telemetry export & command sync
   if(now - m_last_sync_time >= InpSyncIntervalSec)
   {
      SendTelemetryAndSync();
      m_last_sync_time = now;
   }

   // Manage open positions (breakeven logic)
   if(InpAutoBreakeven)
   {
      ManageOpenPositions();
   }

   if(InpShowOnChartPanel)
   {
      UpdateChartDisplay();
   }
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   if(InpShowOnChartPanel)
   {
      UpdateChartDisplay();
   }
}

//+------------------------------------------------------------------+
//| Update on-chart visual display                                   |
//+------------------------------------------------------------------+
void UpdateChartDisplay()
{
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   int spread = (int)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);

   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity  = AccountInfoDouble(ACCOUNT_EQUITY);
   long login     = AccountInfoInteger(ACCOUNT_LOGIN);
   string company = AccountInfoString(ACCOUNT_COMPANY);

   ENUM_ACCOUNT_TRADE_MODE trade_mode = (ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE);
   string trade_mode_str = "DEMO";
   if(trade_mode == ACCOUNT_TRADE_MODE_REAL) trade_mode_str = "REAL (LIVE)";
   else if(trade_mode == ACCOUNT_TRADE_MODE_CONTEST) trade_mode_str = "CONTEST";

   string display_text = "";
   display_text += "====================================================\n";
   display_text += "  BANDI INTELLIGENCE - LOCAL TRADING TERMINAL\n";
   display_text += "====================================================\n";
   display_text += StringFormat("  Broker: %s | Account: %I64d [%s]\n", company, login, trade_mode_str);
   display_text += StringFormat("  Balance: $%.2f | Equity: $%.2f\n", balance, equity);
   display_text += "----------------------------------------------------\n";
   display_text += StringFormat("  Symbol: %s | Bid: %.5f | Ask: %.5f\n", _Symbol, bid, ask);
   display_text += StringFormat("  Live Spread: %d points (Max: %d)\n", spread, InpMaxSpreadPoints);
   display_text += "----------------------------------------------------\n";
   display_text += StringFormat("  TRADING MODE: [%s] | LOCK: [%s]\n",
      m_server_trading_mode,
      m_server_locked ? "LOCKED" : "UNLOCKED");
   
   if(m_kill_switch_active)
   {
      display_text += "  EMERGENCY KILL SWITCH: [🚨 ACTIVE - TRADING HALTED]\n";
   }
   else
   {
      display_text += "  KILL SWITCH: [NORMAL]\n";
   }

   display_text += "----------------------------------------------------\n";
   display_text += "  NEXT HIGH-IMPACT RELEASE:\n";
   display_text += StringFormat("  Event:    %s\n", m_latest_event_title);
   display_text += StringFormat("  Schedule: %s\n", m_latest_event_time);
   display_text += "----------------------------------------------------\n";
   display_text += StringFormat("  SERVER CONNECTION: %s\n", m_webrequest_status);
   display_text += "====================================================\n";

   Comment(display_text);
}

//+------------------------------------------------------------------+
//| Format open positions JSON array                                 |
//+------------------------------------------------------------------+
string GetPositionsJson()
{
   string json = "[";
   int total = PositionsTotal();
   int count = 0;

   for(int i = 0; i < total; i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket > 0)
      {
         string pos_sym = PositionGetString(POSITION_SYMBOL);
         long pos_type  = PositionGetInteger(POSITION_TYPE);
         double vol     = PositionGetDouble(POSITION_VOLUME);
         double open_pr = PositionGetDouble(POSITION_PRICE_OPEN);
         double curr_pr = PositionGetDouble(POSITION_PRICE_CURRENT);
         double sl      = PositionGetDouble(POSITION_SL);
         double tp      = PositionGetDouble(POSITION_TP);
         double profit  = PositionGetDouble(POSITION_PROFIT);
         long magic     = PositionGetInteger(POSITION_MAGIC);

         if(count > 0) json += ",";
         json += StringFormat(
            "{\"ticket\":%I64d,\"symbol\":\"%s\",\"type\":\"%s\",\"volume\":%.2f,\"price_open\":%.5f,\"price_current\":%.5f,\"sl\":%.5f,\"tp\":%.5f,\"profit\":%.2f,\"magic\":%I64d}",
            ticket, pos_sym, (pos_type == POSITION_TYPE_BUY ? "BUY" : "SELL"), vol, open_pr, curr_pr, sl, tp, profit, magic
         );
         count++;
      }
   }
   json += "]";
   return json;
}

//+------------------------------------------------------------------+
//| Send account telemetry, quote data, and sync pending orders      |
//+------------------------------------------------------------------+
void SendTelemetryAndSync()
{
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   int spread = (int)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);

   ENUM_ACCOUNT_TRADE_MODE trade_mode = (ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE);
   string mode_str = (trade_mode == ACCOUNT_TRADE_MODE_REAL) ? "REAL" : "DEMO";

   string positions_json = GetPositionsJson();

   // Build telemetry JSON
   string payload = StringFormat(
      "{\"symbol\":\"%s\",\"bid\":%.5f,\"ask\":%.5f,\"spread\":%d,\"balance\":%.2f,\"equity\":%.2f,\"account\":%I64d,\"broker\":\"%s\",\"trade_mode\":\"%s\",\"positions\":%s}",
      _Symbol, bid, ask, spread,
      AccountInfoDouble(ACCOUNT_BALANCE),
      AccountInfoDouble(ACCOUNT_EQUITY),
      AccountInfoInteger(ACCOUNT_LOGIN),
      AccountInfoString(ACCOUNT_COMPANY),
      mode_str,
      positions_json
   );

   // Save local file backup for offline file-bridge
   int file_handle = FileOpen("bandi_telemetry.json", FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(file_handle != INVALID_HANDLE)
   {
      FileWriteString(file_handle, payload);
      FileClose(file_handle);
   }

   // WebRequest to backend
   char post_data[];
   char result[];
   string result_headers;
   StringToCharArray(payload, post_data, 0, WHOLE_ARRAY, CP_UTF8);

   string headers = "Content-Type: application/json\r\n";
   ResetLastError();
   int res = WebRequest("POST", InpServerUrl, headers, 2000, post_data, result, result_headers);

   if(res == 200 && ArraySize(result) > 0)
   {
      m_webrequest_ok = true;
      m_webrequest_status = "ONLINE (Sync OK)";

      string response_str = CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8);
      ProcessServerResponse(response_str);
   }
   else
   {
      int err = GetLastError();
      m_webrequest_ok = false;
      if(err == 4060)
      {
         m_webrequest_status = "ERROR: WebRequest forbidden! Allow URL in MT5 Options.";
         Print("BANDI Error 4060: Please add 'http://127.0.0.1:8000' to Tools -> Options -> Expert Advisors -> Allow WebRequest");
      }
      else
      {
         m_webrequest_status = StringFormat("OFFLINE (HTTP %d, Err %d)", res, err);
      }
   }
}

//+------------------------------------------------------------------+
//| Simple JSON string value extractor                               |
//+------------------------------------------------------------------+
string ExtractJsonString(const string &json, const string &key)
{
   string search = "\"" + key + "\":\"";
   int start = StringFind(json, search);
   if(start == -1) return "";
   start += StringLen(search);
   int end = StringFind(json, "\"", start);
   if(end == -1) return "";
   return StringSubstr(json, start, end - start);
}

//+------------------------------------------------------------------+
//| Process server response (trading mode, next event, orders)       |
//+------------------------------------------------------------------+
void ProcessServerResponse(const string &json)
{
   // Parse mode and lock state
   string mode = ExtractJsonString(json, "trading_mode");
   if(mode != "") m_server_trading_mode = mode;

   if(StringFind(json, "\"trading_locked\":true") != -1)
      m_server_locked = true;
   else if(StringFind(json, "\"trading_locked\":false") != -1)
      m_server_locked = false;

   if(StringFind(json, "\"kill_switch_active\":true") != -1)
      m_kill_switch_active = true;
   else if(StringFind(json, "\"kill_switch_active\":false") != -1)
      m_kill_switch_active = false;

   // Parse next event
   int ev_idx = StringFind(json, "\"next_event\"");
   if(ev_idx != -1)
   {
      string ev_sub = StringSubstr(json, ev_idx);
      string title = ExtractJsonString(ev_sub, "title");
      string time_sast = ExtractJsonString(ev_sub, "time_sast");
      if(title != "") m_latest_event_title = title;
      if(time_sast != "") m_latest_event_time = time_sast;
   }

   // Check for pending orders
   int orders_idx = StringFind(json, "\"pending_orders\":[");
   if(orders_idx != -1)
   {
      int start_bracket = orders_idx + StringLen("\"pending_orders\":[");
      int end_bracket = StringFind(json, "]", start_bracket);
      if(end_bracket > start_bracket)
      {
         string orders_chunk = StringSubstr(json, start_bracket, end_bracket - start_bracket);
         if(StringLen(orders_chunk) > 5)
         {
            ExecutePendingOrders(orders_chunk);
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Execute orders queued by the decision engine                     |
//+------------------------------------------------------------------+
void ExecutePendingOrders(const string &orders_chunk)
{
   // Re-check EA Hard Safety Gates
   if(m_kill_switch_active)
   {
      Print("BANDI EA: Order rejected. Kill switch is active.");
      return;
   }

   if(m_server_locked || m_server_trading_mode == "OFF" || m_server_trading_mode == "SIGNALS_ONLY")
   {
      Print("BANDI EA: Order rejected. System is locked or in signals-only mode (", m_server_trading_mode, ")");
      return;
   }

   ENUM_ACCOUNT_TRADE_MODE trade_mode = (ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE);
   if(trade_mode == ACCOUNT_TRADE_MODE_REAL)
   {
      // Real account double check
      Print("BANDI EA: LIVE ACCOUNT DETECTED. Verifying server approval...");
   }

   // Extract order parameters
   string order_id = ExtractJsonString(orders_chunk, "order_id");
   string symbol   = ExtractJsonString(orders_chunk, "symbol");
   string action   = ExtractJsonString(orders_chunk, "direction");

   if(symbol == "" || symbol != _Symbol)
   {
      // Order is for another chart symbol or invalid
      return;
   }

   // Extract numbers
   double volume = 0.01;
   int vol_pos = StringFind(orders_chunk, "\"volume\":");
   if(vol_pos != -1)
      volume = StringToDouble(StringSubstr(orders_chunk, vol_pos + 9));

   double sl = 0.0;
   int sl_pos = StringFind(orders_chunk, "\"sl\":");
   if(sl_pos != -1)
      sl = StringToDouble(StringSubstr(orders_chunk, sl_pos + 5));

   double tp = 0.0;
   int tp_pos = StringFind(orders_chunk, "\"tp\":");
   if(tp_pos != -1)
      tp = StringToDouble(StringSubstr(orders_chunk, tp_pos + 5));

   // Pre-execution validation
   if(sl <= 0.0)
   {
      ReportOrderResult(order_id, false, 0, "Rejected: Stop loss is missing or zero.");
      return;
   }

   if(volume <= 0.0 || volume > InpMaxLot)
   {
      ReportOrderResult(order_id, false, 0, StringFormat("Rejected: Volume %.2f exceeds max lot %.2f", volume, InpMaxLot));
      return;
   }

   int spread = (int)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   if(spread > InpMaxSpreadPoints)
   {
      ReportOrderResult(order_id, false, 0, StringFormat("Rejected: Spread %d exceeds max %d", spread, InpMaxSpreadPoints));
      return;
   }

   // Dispatch order via CTrade
   bool success = false;
   ulong ticket = 0;
   string comment = "BANDI:" + order_id;

   if(action == "BUY")
   {
      double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      success = m_trade.Buy(volume, _Symbol, ask, sl, tp, comment);
      ticket = m_trade.ResultDeal();
   }
   else if(action == "SELL")
   {
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      success = m_trade.Sell(volume, _Symbol, bid, sl, tp, comment);
      ticket = m_trade.ResultDeal();
   }

   uint retcode = m_trade.ResultRetcode();
   string desc = m_trade.ResultRetcodeDescription();

   if(success)
   {
      Print("BANDI EA: Order executed successfully! Ticket: ", ticket);
      ReportOrderResult(order_id, true, ticket, StringFormat("Executed at retcode %d (%s)", retcode, desc));
   }
   else
   {
      Print("BANDI EA: Order execution failed! Retcode: ", retcode, " - ", desc);
      ReportOrderResult(order_id, false, 0, StringFormat("Failed: Retcode %d (%s)", retcode, desc));
   }
}

//+------------------------------------------------------------------+
//| Report execution result back to server                           |
//+------------------------------------------------------------------+
void ReportOrderResult(const string order_id, bool success, ulong ticket, const string message)
{
   string payload = StringFormat(
      "{\"order_id\":\"%s\",\"success\":%s,\"ticket\":%I64d,\"message\":\"%s\",\"symbol\":\"%s\"}",
      order_id, success ? "true" : "false", ticket, message, _Symbol
   );

   char post_data[];
   char result[];
   string result_headers;
   StringToCharArray(payload, post_data, 0, WHOLE_ARRAY, CP_UTF8);

   string headers = "Content-Type: application/json\r\n";
   WebRequest("POST", InpResultUrl, headers, 2000, post_data, result, result_headers);
}

//+------------------------------------------------------------------+
//| Manage open positions (e.g. Move SL to breakeven at 1R)          |
//+------------------------------------------------------------------+
void ManageOpenPositions()
{
   int total = PositionsTotal();
   for(int i = total - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket > 0 && PositionGetString(POSITION_SYMBOL) == _Symbol)
      {
         if(PositionGetInteger(POSITION_MAGIC) == InpMagicNumber)
         {
            double open_price = PositionGetDouble(POSITION_PRICE_OPEN);
            double sl = PositionGetDouble(POSITION_SL);
            double tp = PositionGetDouble(POSITION_TP);
            double curr_price = PositionGetDouble(POSITION_PRICE_CURRENT);
            long type = PositionGetInteger(POSITION_TYPE);

            if(sl > 0.0)
            {
               double r_distance = MathAbs(open_price - sl);
               if(r_distance > 0)
               {
                  if(type == POSITION_TYPE_BUY)
                  {
                     // If profit >= 1R and SL is still below open price
                     if(curr_price >= (open_price + r_distance) && sl < open_price)
                     {
                        m_trade.PositionModify(ticket, open_price, tp);
                        Print("BANDI: Moved SL to Breakeven for BUY ticket ", ticket);
                     }
                  }
                  else if(type == POSITION_TYPE_SELL)
                  {
                     // If profit >= 1R and SL is still above open price
                     if(curr_price <= (open_price - r_distance) && (sl > open_price || sl == 0.0))
                     {
                        m_trade.PositionModify(ticket, open_price, tp);
                        Print("BANDI: Moved SL to Breakeven for SELL ticket ", ticket);
                     }
                  }
               }
            }
         }
      }
   }
}
//+------------------------------------------------------------------+
