//+------------------------------------------------------------------+
//| AgenticCalendarExport.mq5                                        |
//| Exports MetaQuotes' economic calendar history to a CSV file for  |
//| AgentICTrader research (algo-research update 2026-10i, Req 29).  |
//|                                                                  |
//| Run it once from the Navigator (drag it onto any chart). It      |
//| writes Common\Files\agentic_calendar_<from>_<to>.csv; then       |
//|   python -m algo_research calendar --import <that file>          |
//|                                                                  |
//| Calendar times are the trade server's; every row carries the     |
//| server's offset from UTC at export, so the import converts them. |
//| Values arrive in millionths, LONG_MIN meaning empty: they are    |
//| written as plain numbers, or left blank.                         |
//+------------------------------------------------------------------+
#property copyright "AgentICTrader"
#property version   "1.00"
#property description "Export the economic calendar's history to CSV for AgentICTrader research"
// No input dialog: it runs at once with the defaults below (a dialog hidden behind other windows cancelled
// every drag on 2026-10-16). Edit the defaults and recompile to change the period or the currencies.

input datetime InpFrom       = D'2024.09.01 00:00';   // first release time (server time)
input datetime InpTo         = 0;                     // last release time; 0 = now
input string   InpCurrencies = "USD,EUR,GBP";          // comma-separated currencies

//--- the importance and time mode as the import expects them
string ImportanceName(const ENUM_CALENDAR_EVENT_IMPORTANCE importance)
  {
   switch(importance)
     {
      case CALENDAR_IMPORTANCE_LOW:      return "LOW";
      case CALENDAR_IMPORTANCE_MODERATE: return "MODERATE";
      case CALENDAR_IMPORTANCE_HIGH:     return "HIGH";
      default:                           return "NONE";
     }
  }

string TimeModeName(const ENUM_CALENDAR_EVENT_TIMEMODE mode)
  {
   switch(mode)
     {
      case CALENDAR_TIMEMODE_DATETIME:  return "DATETIME";
      case CALENDAR_TIMEMODE_DATE:      return "DATE";
      case CALENDAR_TIMEMODE_NOTIME:    return "NOTIME";
      case CALENDAR_TIMEMODE_TENTATIVE: return "TENTATIVE";
      default:                          return "UNKNOWN";
     }
  }

//--- a calendar value: millionths to a number, LONG_MIN to blank
string Number(const long value)
  {
   if(value == LONG_MIN)
      return "";
   return DoubleToString(value / 1000000.0, 6);
  }

//--- commas and quotes would break the CSV
string Clean(string text)
  {
   StringReplace(text, ",", ";");
   StringReplace(text, "\"", "'");
   StringReplace(text, "\n", " ");
   return text;
  }

string Day(const datetime t)
  {
   string text = TimeToString(t, TIME_DATE);
   StringReplace(text, ".", "-");
   return text;
  }

//--- one currency's values, a month at a time: a long first request timed out (error 5401) on 2026-10-16
//--- while the terminal was still downloading the calendar, so each month is retried before giving up
int FetchValues(const string currency, const datetime from, const datetime to, MqlCalendarValue &out[])
  {
   ArrayResize(out, 0);
   datetime start = from;
   while(start < to)
     {
      datetime stop = (datetime)MathMin((double)to, (double)(start + 31 * 86400));
      MqlCalendarValue chunk[];
      int n = -1;
      for(int attempt = 0; attempt < 10 && n < 0; attempt++)
        {
         ResetLastError();
         n = CalendarValueHistory(chunk, start, stop, NULL, currency);
         if(n < 0)
           {
            PrintFormat("AgenticCalendarExport: %s %s, attempt %d failed (error %d)", currency, Day(start),
                        attempt + 1, GetLastError());
            Sleep(3000);
           }
        }
      if(n < 0)
         return -1;
      int have = ArraySize(out);
      ArrayResize(out, have + n);
      for(int i = 0; i < n; i++)
         out[have + i] = chunk[i];
      start = stop;
     }
   return ArraySize(out);
  }

void OnStart()
  {
   datetime to     = (InpTo == 0) ? TimeTradeServer() : InpTo;
   long     offset = (long)(TimeTradeServer() - TimeGMT());
   string   name   = "agentic_calendar_" + Day(InpFrom) + "_" + Day(to) + ".csv";

   int file = FileOpen(name, FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(file == INVALID_HANDLE)
     {
      PrintFormat("AgenticCalendarExport: cannot open %s (error %d)", name, GetLastError());
      return;
     }
   FileWriteString(file, "value_id,event_id,time_server,server_offset_s,currency,country,event,importance,"
                         "time_mode,actual,forecast,previous,revised,unit,multiplier\n");

   string currencies[];
   int count = StringSplit(InpCurrencies, ',', currencies);
   int rows  = 0;
   for(int k = 0; k < count; k++)
     {
      string currency = currencies[k];
      StringTrimLeft(currency);
      StringTrimRight(currency);
      MqlCalendarValue values[];
      int n = FetchValues(currency, InpFrom, to, values);
      if(n < 0)
        {
         PrintFormat("AgenticCalendarExport: %s failed after retries; it is missing from the file", currency);
         continue;
        }
      for(int i = 0; i < n; i++)
        {
         MqlCalendarEvent event;
         if(!CalendarEventById(values[i].event_id, event))
            continue;
         MqlCalendarCountry country;
         if(!CalendarCountryById(event.country_id, country))
            continue;
         string line = StringFormat("%I64u,%I64u,%s,%I64d,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n",
                                    values[i].id, values[i].event_id,
                                    TimeToString(values[i].time, TIME_DATE | TIME_SECONDS), offset,
                                    country.currency, country.code, Clean(event.name),
                                    ImportanceName(event.importance), TimeModeName(event.time_mode),
                                    Number(values[i].actual_value), Number(values[i].forecast_value),
                                    Number(values[i].prev_value), Number(values[i].revised_prev_value),
                                    Clean(EnumToString(event.unit)), Clean(EnumToString(event.multiplier)));
         FileWriteString(file, line);
         rows++;
        }
      PrintFormat("AgenticCalendarExport: %s, %d values", currency, n);
     }
   FileClose(file);
   PrintFormat("AgenticCalendarExport: %d values written to %s\\Files\\%s (server offset %I64d s)",
               rows, TerminalInfoString(TERMINAL_COMMONDATA_PATH), name, offset);
  }
//+------------------------------------------------------------------+
