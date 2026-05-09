export interface I4 {
  today_value: number;
  past_values: number[];      // up to 15 days, oldest → newest
  avg: number;
  ratio: number | null;
  day_count: number;
}

export interface I5 {
  is_ath: boolean;
  ath_price: number | null;
  ath_date: string | null;
  days_since_ath: number | null;
  year_high: number | null;       // 52-week high price
  year_high_date: string | null;  // date of 52-week high
}

export interface I6 {
  nasdaq_from_open_pct: number;
  nasdaq_from_prev_close_pct: number;
}

export interface StockResult {
  rank: number;
  symbol: string;
  rt_price: number;
  open_price: number;
  prev_close: number;
  today_high: number;
  today_low: number;
  scrape_error: string | null;
  i1: number | null;
  i2: number | null;
  i3: number | null;
  i4: I4;
  i5: I5;
  i6: I6;
}

export interface NasdaqResult {
  rt_level: number;
  open_level: number;
  prev_close: number;
  from_open_pct: number;
  from_prev_close_pct: number;
  error: string | null;
}

export interface DashboardData {
  refreshed_at: string;       // ISO 8601
  nasdaq: NasdaqResult;
  stocks: StockResult[];
}
