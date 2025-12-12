"""
Finnhub data source for US stocks (basic info, price, dividends, financials).
Requires FINNHUB_API_KEY in environment.
"""
import os
import time
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import requests
import pandas as pd

from .data_source_interface import FinancialDataSource, NoDataFoundError, DataSourceError

logger = logging.getLogger(__name__)


class FinnhubDataSource(FinancialDataSource):
    BASE_URL = "https://finnhub.io/api/v1"

    def __init__(self):
        self.api_key = os.getenv("FINNHUB_API_KEY")
        if not self.api_key:
            logger.warning("FINNHUB_API_KEY not set. FinnhubDataSource will fail without it.")
        # Simple rate limit: 1 req / 1.1s (free tier 60/min)
        self._last_req_ts = 0.0
        self._min_interval = 1.1

    def _throttle(self):
        elapsed = time.time() - self._last_req_ts
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_req_ts = time.time()

    def _normalize_ticker(self, code: str) -> str:
        return code.strip().upper() if code else code

    def _request(self, path: str, params: Dict) -> Dict:
        if not self.api_key:
            raise DataSourceError("FINNHUB_API_KEY missing.")
        self._throttle()
        params = params.copy()
        params["token"] = self.api_key
        url = f"{self.BASE_URL}{path}"
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 429:
            raise DataSourceError("Finnhub rate limit (429).")
        if not resp.ok:
            raise DataSourceError(f"Finnhub error {resp.status_code}: {resp.text}")
        try:
            return resp.json()
        except Exception as e:
            raise DataSourceError(f"Finnhub JSON decode error: {e}")

    # --- Core implemented methods ---
    def get_stock_basic_info(self, code: str, fields: Optional[List[str]] = None) -> pd.DataFrame:
        code = self._normalize_ticker(code)
        data = self._request("/stock/profile2", {"symbol": code})
        if not data or not data.get("ticker"):
            raise NoDataFoundError(f"No basic info for {code}")
        df = pd.DataFrame([{
            "code": code,
            "name": data.get("name"),
            "market": data.get("market"),
            "locale": data.get("country"),
            "primary_exchange": data.get("exchange"),
            "currency": data.get("currency"),
            "active": True if data.get("ticker") else False,
            "sic_description": data.get("finnhubIndustry"),
        }])
        if fields:
            keep = [f for f in fields if f in df.columns]
            if keep:
                df = df[keep]
        return df

    def get_historical_k_data(
        self,
        code: str,
        start_date: str,
        end_date: str,
        frequency: str = "d",
        adjust_flag: str = "3",
        fields: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        code = self._normalize_ticker(code)
        if frequency != "d":
            raise ValueError("Finnhub only supports daily ('d') frequency in this implementation.")
        try:
            sd = datetime.strptime(start_date, "%Y-%m-%d")
            ed = datetime.strptime(end_date, "%Y-%m-%d")
        except Exception:
            raise ValueError("start_date/end_date must be YYYY-MM-DD")

        data = self._request("/stock/candle", {
            "symbol": code,
            "resolution": "D",
            "from": int(sd.timestamp()),
            "to": int(ed.timestamp())
        })
        if data.get("s") != "ok":
            raise NoDataFoundError(f"No historical data for {code} between {start_date} and {end_date}")

        df = pd.DataFrame({
            "date": pd.to_datetime(data["t"], unit="s").strftime("%Y-%m-%d"),
            "code": code,
            "open": data["o"],
            "high": data["h"],
            "low": data["l"],
            "close": data["c"],
            "volume": data["v"],
        })
        df["preclose"] = df["close"].shift(1)
        df["pctChg"] = ((df["close"] - df["preclose"]) / df["preclose"] * 100).round(2)
        df["amount"] = (df["volume"] * df["close"]).round(2)
        df["adjustflag"] = adjust_flag
        df["turn"] = 0.0
        df["tradestatus"] = "1"
        df["isST"] = "0"
        df["peTTM"] = None
        df["pbMRQ"] = None
        df["psTTM"] = None
        df["pcfNcfTTM"] = None

        if fields:
            base = ["date", "code"]
            keep = base + [f for f in fields if f in df.columns]
            df = df[keep]
        return df

    def get_dividend_data(self, code: str, year: str, year_type: str = "report") -> pd.DataFrame:
        code = self._normalize_ticker(code)
        start = f"{year}-01-01"
        end = f"{year}-12-31"
        data = self._request("/stock/dividend", {"symbol": code, "from": start, "to": end})
        if not data:
            raise NoDataFoundError(f"No dividend data for {code} in {year}")
        df = pd.DataFrame(data)
        if df.empty:
            raise NoDataFoundError(f"No dividend data for {code} in {year}")
        df["date"] = pd.to_datetime(df["paymentDate"]).dt.strftime("%Y-%m-%d")
        df = df.rename(columns={"amount": "dividend"})
        df["code"] = code
        return df[["date", "dividend", "code"]]

    # --- Financial statements (quarterly) ---
    def _fetch_financials(self, code: str, statement: str):
        code = self._normalize_ticker(code)
        # statement: 'bs', 'is', 'cf'
        data = self._request("/stock/financials", {
            "symbol": code,
            "statement": statement,
            "freq": "quarterly"
        })
        items = data.get("data") or []
        if not items:
            raise NoDataFoundError(f"No {statement} data for {code}")
        df = pd.DataFrame(items)
        if df.empty:
            raise NoDataFoundError(f"No {statement} data for {code}")
        # Normalize date
        if "reportDate" in df.columns:
            df["date"] = pd.to_datetime(df["reportDate"]).dt.strftime("%Y-%m-%d")
        else:
            df["date"] = None
        df["code"] = code
        return df

    def get_profit_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        df = self._fetch_financials(code, "is")
        df = df[df["date"].str.startswith(str(year))]
        if df.empty:
            raise NoDataFoundError(f"No income statement for {code} in {year}")
        keep = ["date", "code", "revenue", "netIncome", "grossProfit", "ebit", "eps"]
        return df[[c for c in keep if c in df.columns]]

    def get_balance_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        df = self._fetch_financials(code, "bs")
        df = df[df["date"].str.startswith(str(year))]
        if df.empty:
            raise NoDataFoundError(f"No balance sheet for {code} in {year}")
        keep = ["date", "code", "totalAssets", "totalLiabilities", "totalEquity", "cashAndCashEquivalents"]
        return df[[c for c in keep if c in df.columns]]

    def get_cash_flow_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        df = self._fetch_financials(code, "cf")
        df = df[df["date"].str.startswith(str(year))]
        if df.empty:
            raise NoDataFoundError(f"No cash flow for {code} in {year}")
        keep = ["date", "code", "cashFlowFromOperations", "cashFlowFromInvesting", "cashFlowFromFinancing", "netCashFlow"]
        return df[[c for c in keep if c in df.columns]]

    # --- Not implemented / return empty ---
    def get_trade_dates(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        return pd.DataFrame()

    def get_all_stock(self, date: Optional[str] = None) -> pd.DataFrame:
        return pd.DataFrame(columns=["code", "code_name", "tradeStatus"])

    def get_stock_industry(self, code: Optional[str] = None, date: Optional[str] = None) -> pd.DataFrame:
        return pd.DataFrame()

    def get_deposit_rate_data(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        return pd.DataFrame()

    def get_loan_rate_data(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        return pd.DataFrame()

    def get_required_reserve_ratio_data(self, start_date: Optional[str] = None, end_date: Optional[str] = None, year_type: str = '0') -> pd.DataFrame:
        return pd.DataFrame()

    def get_money_supply_data_month(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        return pd.DataFrame()

    def get_money_supply_data_year(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        return pd.DataFrame()

    def get_growth_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        return pd.DataFrame()

    def get_operation_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        return pd.DataFrame()

    def get_dupont_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        return pd.DataFrame()

    def get_stock_analysis(self, code: str, analysis_type: str = "fundamental") -> pd.DataFrame:
        return pd.DataFrame()

    def get_adjust_factor_data(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        return pd.DataFrame()

    def get_performance_express_report(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        return pd.DataFrame()

    def get_forecast_report(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        return pd.DataFrame()

    def crawl_news(self, query: str, top_k: int = 10) -> str:
        # Use company-news endpoint
        try:
            data = self._request("/company-news", {
                "symbol": query,
                "from": (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d"),
                "to": datetime.utcnow().strftime("%Y-%m-%d")
            })
            if not data:
                return "No news found."
            items = data[:top_k]
            lines = []
            for i, item in enumerate(items, 1):
                headline = item.get("headline", "")
                summary = item.get("summary", "")
                url = item.get("url", "")
                pub = item.get("datetime")
                if pub:
                    pub = datetime.utcfromtimestamp(pub).strftime("%Y-%m-%d")
                lines.append(f"{i}. {headline} ({pub})\n{summary}\n{url}")
            return "\n\n".join(lines) if lines else "No news found."
        except Exception as e:
            logger.error(f"Finnhub news error: {e}")
            return "No news found."
"""
Finnhub data source for US stocks (as Yahoo replacement).
Implements core pieces: basic info, daily K-line, dividends, financial statements (bs/is/cf), and company news.
"""
import os
import time
import logging
from datetime import datetime, timedelta
from typing import Optional, List

import requests
import pandas as pd

from .data_source_interface import FinancialDataSource, NoDataFoundError, DataSourceError

logger = logging.getLogger(__name__)


class FinnhubDataSource(FinancialDataSource):
    BASE_URL = "https://finnhub.io/api/v1"

    def __init__(self):
        self.api_key = os.getenv("FINNHUB_API_KEY")
        if not self.api_key:
            logger.warning("FINNHUB_API_KEY not set. FinnhubDataSource will fail without it.")
        self._last_request_ts = 0.0
        self._min_interval = 1.0  # conservative: 1 req/sec for free tier safety

    def _throttle(self):
        elapsed = time.time() - self._last_request_ts
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_ts = time.time()

    def _request(self, path: str, params: dict) -> dict:
        if not self.api_key:
            raise DataSourceError("FINNHUB_API_KEY missing.")
        self._throttle()
        q = params.copy()
        q["token"] = self.api_key
        url = f"{self.BASE_URL}{path}"
        resp = requests.get(url, params=q, timeout=15)
        if resp.status_code == 429:
            raise DataSourceError("Finnhub rate limit (429).")
        if not resp.ok:
            raise DataSourceError(f"Finnhub error {resp.status_code}: {resp.text}")
        try:
            return resp.json()
        except Exception as e:
            raise DataSourceError(f"Finnhub JSON decode error: {e}")

    def _normalize_ticker(self, code: str) -> str:
        return code.strip().upper()

    # --- Basic info ---
    def get_stock_basic_info(self, code: str, fields: Optional[List[str]] = None) -> pd.DataFrame:
        code = self._normalize_ticker(code)
        data = self._request("/stock/profile2", {"symbol": code})
        if not data or "name" not in data:
            raise NoDataFoundError(f"No basic info for {code}")
        df = pd.DataFrame([{
            "code": code,
            "name": data.get("name"),
            "market": "stocks",
            "locale": data.get("country"),
            "primary_exchange": data.get("exchange"),
            "currency": data.get("currency"),
            "active": True,
            "sic_description": data.get("finnhubIndustry")
        }])
        if fields:
            keep = [f for f in fields if f in df.columns]
            if keep:
                df = df[keep]
        return df

    # --- Historical K-line (daily) ---
    def get_historical_k_data(
        self,
        code: str,
        start_date: str,
        end_date: str,
        frequency: str = "d",
        adjust_flag: str = "3",
        fields: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        code = self._normalize_ticker(code)
        if frequency != "d":
            raise ValueError("Finnhub only implemented daily frequency here.")
        try:
            sd = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
            ed = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp())
        except Exception:
            raise ValueError("start_date/end_date must be YYYY-MM-DD")

        data = self._request("/stock/candle", {"symbol": code, "resolution": "D", "from": sd, "to": ed})
        if data.get("s") != "ok":
            raise NoDataFoundError(f"No historical data for {code} between {start_date} and {end_date}")

        # Build DataFrame
        df = pd.DataFrame({
            "date": pd.to_datetime(data["t"], unit="s").strftime("%Y-%m-%d"),
            "open": data["o"],
            "high": data["h"],
            "low": data["l"],
            "close": data["c"],
            "volume": data["v"],
        })
        df["code"] = code
        df["preclose"] = df["close"].shift(1)
        df["pctChg"] = ((df["close"] - df["preclose"]) / df["preclose"] * 100).round(2)
        df["amount"] = (df["volume"] * df["close"]).round(2)
        df["adjustflag"] = adjust_flag
        df["turn"] = 0.0
        df["tradestatus"] = "1"
        df["isST"] = "0"
        df["peTTM"] = None
        df["pbMRQ"] = None
        df["psTTM"] = None
        df["pcfNcfTTM"] = None

        if fields:
            base = ["date", "code"]
            keep = base + [f for f in fields if f in df.columns]
            df = df[keep]
        return df

    # --- Dividends ---
    def get_dividend_data(self, code: str, year: str, year_type: str = "report") -> pd.DataFrame:
        code = self._normalize_ticker(code)
        # fetch last 5 years window to cover year filter
        start = (datetime.utcnow() - timedelta(days=5*365)).strftime("%Y-%m-%d")
        end = datetime.utcnow().strftime("%Y-%m-%d")
        data = self._request("/stock/dividend", {"symbol": code, "from": start, "to": end})
        results = data if isinstance(data, list) else data.get("data") or []
        if not results:
            raise NoDataFoundError(f"No dividend data for {code}")
        df = pd.DataFrame(results)
        if "paymentDate" in df.columns:
            df["date"] = pd.to_datetime(df["paymentDate"]).dt.strftime("%Y-%m-%d")
        elif "payDate" in df.columns:
            df["date"] = pd.to_datetime(df["payDate"]).dt.strftime("%Y-%m-%d")
        else:
            df["date"] = pd.to_datetime(df.get("declaredDate")).dt.strftime("%Y-%m-%d")
        df["dividend"] = df.get("amount") if "amount" in df.columns else df.get("cashAmount")
        df["code"] = code
        if year:
            df = df[df["date"].str.startswith(str(year))]
        return df[["date", "dividend", "code"]]

    # --- Financial statements (basic mapping) ---
    def _financials(self, code: str, statement: str, freq: str = "quarterly") -> pd.DataFrame:
        code = self._normalize_ticker(code)
        data = self._request("/stock/financials", {"symbol": code, "statement": statement, "freq": freq})
        results = data.get("data") or []
        if not results:
            raise NoDataFoundError(f"No {statement} data for {code}")
        df = pd.DataFrame(results)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df["code"] = code
        return df

    def get_profit_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        df = self._financials(code, "is", "quarterly")
        if "date" in df.columns:
            df = df[df["date"].str.startswith(str(year))]
        return df

    def get_balance_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        df = self._financials(code, "bs", "quarterly")
        if "date" in df.columns:
            df = df[df["date"].str.startswith(str(year))]
        return df

    def get_cash_flow_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        df = self._financials(code, "cf", "quarterly")
        if "date" in df.columns:
            df = df[df["date"].str.startswith(str(year))]
        return df

    def get_growth_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        # Not directly provided; return empty to avoid hallucination
        return pd.DataFrame()

    def get_operation_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        return pd.DataFrame()

    def get_dupont_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        return pd.DataFrame()

    # --- News ---
    def crawl_news(self, query: str, top_k: int = 10) -> str:
        # Finnhub company-news requires symbol; here use query as symbol when possible
        symbol = self._normalize_ticker(query)
        end = datetime.utcnow().date()
        start = end - timedelta(days=14)
        try:
            data = self._request("/company-news", {"symbol": symbol, "from": start.isoformat(), "to": end.isoformat()})
            if not data:
                return "No news found."
            items = data[:top_k]
            lines = []
            for i, n in enumerate(items, 1):
                headline = n.get("headline", "")
                summary = n.get("summary", "")
                url = n.get("url", "")
                dt = n.get("datetime")
                if dt:
                    dt = datetime.utcfromtimestamp(dt).strftime("%Y-%m-%d %H:%M")
                lines.append(f"{i}. {headline} ({dt})\n{summary}\n{url}")
            return "\n\n".join(lines) if lines else "No news found."
        except Exception as e:
            logger.error(f"Finnhub news error for {query}: {e}")
            return "No news found."

    # --- Unimplemented / placeholders ---
    def get_trade_dates(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        return pd.DataFrame()

    def get_all_stock(self, date: Optional[str] = None) -> pd.DataFrame:
        return pd.DataFrame(columns=["code", "code_name", "tradeStatus"])

    def get_stock_industry(self, code: Optional[str] = None, date: Optional[str] = None) -> pd.DataFrame:
        return pd.DataFrame()

    def get_deposit_rate_data(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        return pd.DataFrame()

    def get_loan_rate_data(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        return pd.DataFrame()

    def get_required_reserve_ratio_data(self, start_date: Optional[str] = None, end_date: Optional[str] = None, year_type: str = '0') -> pd.DataFrame:
        return pd.DataFrame()

    def get_money_supply_data_month(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        return pd.DataFrame()

    def get_money_supply_data_year(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        return pd.DataFrame()

    def get_stock_analysis(self, code: str, analysis_type: str = "fundamental") -> pd.DataFrame:
        return pd.DataFrame()

    def get_adjust_factor_data(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        return pd.DataFrame()

    def get_performance_express_report(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        return pd.DataFrame()

    def get_forecast_report(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        return pd.DataFrame()
