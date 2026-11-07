//+------------------------------------------------------------------+
//|                                                        Bandi.mq5 |
//|                                  Copyright 2026, BANDI Project   |
//|                       https://github.com/KuronaiZuko1/Collab.git |
//+------------------------------------------------------------------+
#property copyright   "BANDI Project"
#property link        "https://github.com/KuronaiZuko1/Collab.git"
#property version     "1.00"
#property description "BANDI - Local-First Automated Trading Intelligence & Alert Bridge"

//--- Input parameters
input group "=== BANDI Server Settings ==="
input string   InpServerUrl         = "http://127.0.0.1:8000/api/mt5/sync"; // Backend Sync Endpoint
input int      InpSyncIntervalSec   = 5;                                    // Telemetry Interval (sec)

input group "=== Display & Safety ==="
input bool     InpShowOnChartPanel  = true;                                 // Show On-Chart Monitor

//--- Global variables
datetime       m_last_sync_time     = 0;
string         m_latest_event_title = "Scanning upcoming releases...";
string         m_latest_event_time  = "30m Alert Guard Active";

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("BANDI: Initializing MetaTrader 5 Bridge...");

   // Read-only safety guard
   Print("BANDI: Operating strictly in READ-ONLY mode. Live order dispatch disabled.");

   EventSetTimer(1); // 1-second timer for countdown & telemetry
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

   // Periodic telemetry export
   if(now - m_last_sync_time >= InpSyncIntervalSec)
   {
      SendTelemetry();
      m_last_sync_time = now;
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

   string display_text = "";
   display_text += "====================================================\n";
   display_text += "  BANDI INTELLIGENCE - LOCAL MONITOR\n";
   display_text += "====================================================\n";
   display_text += StringFormat("  Broker: %s | Account: %I64d\n", company, login);
   display_text += StringFormat("  Balance: $%.2f | Equity: $%.2f\n", balance, equity);
   display_text += "----------------------------------------------------\n";
   display_text += StringFormat("  Symbol: %s | Bid: %.5f | Ask: %.5f\n", _Symbol, bid, ask);
   display_text += StringFormat("  Live Spread: %d points\n", spread);
   display_text += "----------------------------------------------------\n";
   display_text += "  ECONOMIC CALENDAR ALERT STATUS:\n";
   display_text += StringFormat("  Next Event: %s\n", m_latest_event_title);
   display_text += StringFormat("  Schedule:   %s\n", m_latest_event_time);
   display_text += "----------------------------------------------------\n";
   display_text += "  SAFETY LOCK: [ACTIVE] - Live trading execution locked\n";
   display_text += "====================================================\n";

   Comment(display_text);
}

//+------------------------------------------------------------------+
//| Send account and market telemetry to BANDI server                |
//+------------------------------------------------------------------+
void SendTelemetry()
{
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   int spread = (int)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);

   // Prepare JSON payload
   string json = StringFormat(
      "{\"symbol\":\"%s\",\"bid\":%.5f,\"ask\":%.5f,\"spread\":%d,\"balance\":%.2f,\"equity\":%.2f,\"account\":%I64d,\"broker\":\"%s\"}",
      _Symbol,
      bid,
      ask,
      spread,
      AccountInfoDouble(ACCOUNT_BALANCE),
      AccountInfoDouble(ACCOUNT_EQUITY),
      AccountInfoInteger(ACCOUNT_LOGIN),
      AccountInfoString(ACCOUNT_COMPANY)
   );

   // Save to shared local file in MQL5/Files for offline sync
   int file_handle = FileOpen("bandi_telemetry.json", FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(file_handle != INVALID_HANDLE)
   {
      FileWriteString(file_handle, json);
      FileClose(file_handle);
   }

   // Attempt HTTP WebRequest if enabled in terminal settings
   char post_data[];
   char result[];
   string result_headers;
   StringToCharArray(json, post_data, 0, WHOLE_ARRAY, CP_UTF8);
   
   string headers = "Content-Type: application/json\r\n";
   WebRequest("POST", InpServerUrl, headers, 1000, post_data, result, result_headers);
}
//+------------------------------------------------------------------+
