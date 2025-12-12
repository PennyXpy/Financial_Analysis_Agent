"""
Polygon.io data source for US stocks.
Only implements the subset we need: basic info and historical K-line.
"""
import os
import time
import logging
from datetime import datetime
from typing import Optional, List
import requests
import pandas as pd

from .data_source_interface import FinancialDataSource, NoDataFoundError, DataSourceError

logger = logging.getLogger(__name__)


class PolygonDataSource(FinancialDataSource):
    BASE_URL = "https://api.polygon.io"

    def __init__(self):
        self.api_key = os.getenv("POLYGON_API_KEY")
        if not self.api_key:
            logger.warning("POLYGON_API_KEY not set. PolygonDataSource will fail without it.")
        # Simple rate limit: 1 request / 1.2s
        self._last_request_ts = 0.0
        self._min_interval = 1.2

    def _throttle(self):
        elapsed = time.time() - self._last_request_ts
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_ts = time.time()

    def _request(self, path: str, params: dict) -> dict:
        if not self.api_key:
            raise DataSourceError("POLYGON_API_KEY missing.")
        self._throttle()
        params = params.copy()
        params["apiKey"] = self.api_key
        url = f"{self.BASE_URL}{path}"
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 429:
            raise DataSourceError("Polygon rate limit (429).")
        if not resp.ok:
            raise DataSourceError(f"Polygon error {resp.status_code}: {resp.text}")
        try:
            return resp.json()
        except Exception as e:
            raise DataSourceError(f"Polygon JSON decode error: {e}")

    def _normalize_ticker(self, code: str) -> str:
        return code.strip().upper()

    # --- Implemented methods ---
    def get_stock_basic_info(self, code: str, fields: Optional[List[str]] = None) -> pd.DataFrame:
        code = self._normalize_ticker(code)
        data = self._request(f"/v3/reference/tickers/{code}", params={})
        if data.get("status") != "OK" or "results" not in data:
            raise NoDataFoundError(f"No basic info for {code}")
        res = data["results"]
        df = pd.DataFrame([{
            "code": code,
            "name": res.get("name"),
            "market": res.get("market"),
            "locale": res.get("locale"),
            "primary_exchange": res.get("primary_exchange"),
            "currency": res.get("currency_name"),
            "active": res.get("active"),
            "sic_description": res.get("sic_description"),
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
        """
        Uses Polygon aggregates endpoint.
        frequency supports: d (1 day) or intraday not supported here.
        adjust_flag is ignored; Polygon returns adjusted by default when adjusted=true.
        """
        code = self._normalize_ticker(code)
        freq_map = {"d": ("1", "day")}
        if frequency not in freq_map:
            raise ValueError(f"Unsupported frequency {frequency} for Polygon (only 'd').")
        mult, timespan = freq_map[frequency]
        # Polygon expects date strings YYYY-MM-DD
        try:
            sd = datetime.strptime(start_date, "%Y-%m-%d").date()
            ed = datetime.strptime(end_date, "%Y-%m-%d").date()
        except Exception:
            raise ValueError("start_date/end_date must be YYYY-MM-DD")

        path = f"/v2/aggs/ticker/{code}/range/{mult}/{timespan}/{sd}/{ed}"
        data = self._request(path, params={"adjusted": "true", "sort": "asc", "limit": 5000})
        results = data.get("results") or []
        if not results:
            raise NoDataFoundError(f"No historical data for {code} between {start_date} and {end_date}")

        df = pd.DataFrame(results)
        # Map fields
        df["date"] = pd.to_datetime(df["t"], unit="ms").dt.strftime("%Y-%m-%d")
        df["code"] = code
        df.rename(columns={
            "o": "open",
            "h": "high",
            "l": "low",
            "c": "close",
            "v": "volume"
        }, inplace=True)
        # Add placeholders to align with Baostock-style fields
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

        # Reorder fields if requested
        if fields:
            base = ["date", "code"]
            keep = base + [f for f in fields if f in df.columns]
            df = df[keep]
        return df

    def get_dividend_data(self, code: str, year: str, year_type: str = "report") -> pd.DataFrame:
        code = self._normalize_ticker(code)
        data = self._request("/v3/reference/dividends", params={"ticker": code, "limit": 1000})
        results = data.get("results") or []
        if not results:
            raise NoDataFoundError(f"No dividend data for {code}")
        df = pd.DataFrame(results)
        df["date"] = pd.to_datetime(df["declaration_date"]).dt.strftime("%Y-%m-%d")
        df = df.rename(columns={"cash_amount": "dividend"})
        df["code"] = code
        if year:
            df = df[df["date"].str.startswith(str(year))]
        return df[["date", "dividend", "code"]]

    # --- Unimplemented methods (return empty DataFrame or raise) ---
    def get_trade_dates(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        return pd.DataFrame()

    def get_all_stock(self, date: Optional[str] = None) -> pd.DataFrame:
        return pd.DataFrame(columns=["code", "code_name", "tradeStatus"])

    def get_stock_industry(self, code: Optional[str] = None, date: Optional[str] = None) -> pd.DataFrame:
        # Not available directly; return empty to avoid hallucination
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

    def get_balance_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        raise NoDataFoundError("Polygon balance sheet not implemented.")

    def get_cash_flow_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        raise NoDataFoundError("Polygon cash flow not implemented.")

    def get_dupont_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        return pd.DataFrame()

    def get_profit_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        raise NoDataFoundError("Polygon profit data not implemented.")

    def get_operation_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        return pd.DataFrame()

    def get_stock_analysis(self, code: str, analysis_type: str = "fundamental") -> pd.DataFrame:
        return pd.DataFrame()

    def get_adjust_factor_data(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        return pd.DataFrame()

    def get_performance_express_report(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        return pd.DataFrame()

    def get_forecast_report(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        return pd.DataFrame()
