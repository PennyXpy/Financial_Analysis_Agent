# Baostock-based implementation of FinancialDataSource
import baostock as bs
import pandas as pd
from typing import List, Optional
import logging
from .data_source_interface import FinancialDataSource, DataSourceError, NoDataFoundError, LoginError
from .utils import (
    baostock_login_context,
    fetch_financial_data,
    fetch_index_constituent_data,
    fetch_macro_data,
    fetch_generic_data,
    format_fields
)
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Default K-line fields
DEFAULT_K_FIELDS = [
    "date", "code", "open", "high", "low", "close", "preclose",
    "volume", "amount", "adjustflag", "turn", "tradestatus",
    "pctChg", "peTTM", "pbMRQ", "psTTM", "pcfNcfTTM", "isST"
]

# Default basic stock fields
DEFAULT_BASIC_FIELDS = ["code", "tradeStatus", "code_name"]


class BaostockDataSource(FinancialDataSource):
    """
    Baostock implementation of FinancialDataSource
    """

    def _format_fields(self, fields: Optional[List[str]], default_fields: List[str]) -> str:
        """
        Format field list into comma-separated string for Baostock API

        Args:
            fields: user-requested field list (optional)
            default_fields: default fields if fields is None

        Returns:
            Comma-separated string of fields

        Raises:
            ValueError: if any field is not string
        """
        return format_fields(fields, default_fields)

    def get_profit_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        """Fetch quarterly profitability data"""
        return fetch_financial_data(bs.query_profit_data, "Profitability", code, year, quarter)

    def get_operation_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        """Fetch quarterly operation capability data"""
        return fetch_financial_data(bs.query_operation_data, "Operation Capability", code, year, quarter)

    def get_growth_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        """Fetch quarterly growth capability data"""
        return fetch_financial_data(bs.query_growth_data, "Growth Capability", code, year, quarter)

    def get_balance_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        """Fetch quarterly balance sheet data"""
        return fetch_financial_data(bs.query_balance_data, "Balance Sheet", code, year, quarter)

    def get_cash_flow_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        """Fetch quarterly cash flow data"""
        return fetch_financial_data(bs.query_cash_flow_data, "Cash Flow", code, year, quarter)

    def get_dupont_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        """Fetch quarterly DuPont analysis data"""
        return fetch_financial_data(bs.query_dupont_data, "DuPont Analysis", code, year, quarter)

    def get_sz50_stocks(self, date: Optional[str] = None) -> pd.DataFrame:
        """Fetch SZSE 50 index constituents"""
        return fetch_index_constituent_data(bs.query_sz50_stocks, "SZSE 50", date)

    def get_hs300_stocks(self, date: Optional[str] = None) -> pd.DataFrame:
        """Fetch CSI 300 index constituents"""
        return fetch_index_constituent_data(bs.query_hs300_stocks, "CSI 300", date)

    def get_zz500_stocks(self, date: Optional[str] = None) -> pd.DataFrame:
        """Fetch CSI 500 index constituents"""
        return fetch_index_constituent_data(bs.query_zz500_stocks, "CSI 500", date)

    def get_deposit_rate_data(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        """Fetch benchmark deposit rates"""
        return fetch_macro_data(bs.query_deposit_rate_data, "Deposit Rate", start_date, end_date)

    def get_loan_rate_data(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        """Fetch benchmark loan rates"""
        return fetch_macro_data(bs.query_loan_rate_data, "Loan Rate", start_date, end_date)

    def get_required_reserve_ratio_data(self, start_date: Optional[str] = None, end_date: Optional[str] = None,
                                        year_type: str = '0') -> pd.DataFrame:
        """Fetch required reserve ratio data"""
        return fetch_macro_data(bs.query_required_reserve_ratio_data, "Required Reserve Ratio", start_date, end_date,
                                yearType=year_type)

    def get_money_supply_data_month(self, start_date: Optional[str] = None,
                                    end_date: Optional[str] = None) -> pd.DataFrame:
        """Fetch monthly money supply data (M0, M1, M2)"""
        return fetch_macro_data(bs.query_money_supply_data_month, "Monthly Money Supply", start_date, end_date)

    def get_money_supply_data_year(self, start_date: Optional[str] = None,
                                   end_date: Optional[str] = None) -> pd.DataFrame:
        """Fetch yearly money supply data (M0, M1, M2 - year-end balance)"""
        return fetch_macro_data(bs.query_money_supply_data_year, "Yearly Money Supply", start_date, end_date)

    def get_trade_dates(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        """Fetch trading calendar for the specified date range"""
        return fetch_macro_data(bs.query_trade_dates, "Trade Dates", start_date, end_date)

    def get_historical_k_data(
            self,
            code: str,
            start_date: str,
            end_date: str,
            frequency: str = "d",
            adjust_flag: str = "3",
            fields: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """Fetch historical K-line data"""
        logger.info(f"Fetching K-data for {code} ({start_date} to {end_date}), freq={frequency}, adjust={adjust_flag}")
        try:
            formatted_fields = self._format_fields(fields, DEFAULT_K_FIELDS)
            logger.debug(f"Requesting fields from Baostock: {formatted_fields}")
            with baostock_login_context():
                rs = bs.query_history_k_data_plus(
                    code,
                    formatted_fields,
                    start_date=start_date,
                    end_date=end_date,
                    frequency=frequency,
                    adjustflag=adjust_flag
                )
                if rs.error_code != '0':
                    logger.error(f"Baostock API error (K-data) for {code}: {rs.error_msg} (code: {rs.error_code})")
                    if "no record found" in rs.error_msg.lower() or rs.error_code == '10002':
                        raise NoDataFoundError(f"No historical data found for {code}. Baostock msg: {rs.error_msg}")
                    else:
                        raise DataSourceError(
                            f"Baostock API error fetching K-data: {rs.error_msg} (code: {rs.error_code})")
                data_list = []
                while rs.next():
                    data_list.append(rs.get_row_data())
                if not data_list:
                    logger.warning(f"No historical data found for {code} (empty result set).")
                    raise NoDataFoundError(f"No historical data found for {code} (empty result set).")
                result_df = pd.DataFrame(data_list, columns=rs.fields)
                logger.info(f"Retrieved {len(result_df)} records for {code}.")
                return result_df
        except (LoginError, NoDataFoundError, DataSourceError, ValueError) as e:
            logger.warning(f"Caught known error fetching K-data for {code}: {type(e).__name__}")
            raise e
        except Exception as e:
            logger.exception(f"Unexpected error fetching K-data for {code}: {e}")
            raise DataSourceError(f"Unexpected error fetching K-data for {code}: {e}")

    def get_stock_basic_info(self, code: str, fields: Optional[List[str]] = None) -> pd.DataFrame:
        """Fetch basic stock information"""
        logger.info(f"Fetching basic info for {code}")
        try:
            logger.debug(f"Requested fields: {fields}")
            with baostock_login_context():
                rs = bs.query_stock_basic(code=code)
                if rs.error_code != '0':
                    logger.error(f"Baostock API error (Basic Info) for {code}: {rs.error_msg} (code: {rs.error_code})")
                    if "no record found" in rs.error_msg.lower() or rs.error_code == '10002':
                        raise NoDataFoundError(f"No basic info found for {code}. Baostock msg: {rs.error_msg}")
                    else:
                        raise DataSourceError(
                            f"Baostock API error fetching basic info: {rs.error_msg} (code: {rs.error_code})")
                data_list = []
                while rs.next():
                    data_list.append(rs.get_row_data())
                if not data_list:
                    logger.warning(f"No basic info found for {code} (empty result set).")
                    raise NoDataFoundError(f"No basic info found for {code} (empty result set).")
                result_df = pd.DataFrame(data_list, columns=rs.fields)
                logger.info(f"Retrieved basic info for {code}. Columns: {result_df.columns.tolist()}")
                if fields:
                    available_cols = [col for col in fields if col in result_df.columns]
                    if not available_cols:
                        raise ValueError(f"None of the requested fields {fields} are available.")
                    result_df = result_df[available_cols]
                return result_df
        except (LoginError, NoDataFoundError, DataSourceError, ValueError) as e:
            logger.warning(f"Caught known error fetching basic info for {code}: {type(e).__name__}")
            raise e
        except Exception as e:
            logger.exception(f"Unexpected error fetching basic info for {code}: {e}")
            raise DataSourceError(f"Unexpected error fetching basic info for {code}: {e}")

    def get_dividend_data(self, code: str, year: str, year_type: str = "report") -> pd.DataFrame:
        """Fetch dividend data"""
        return fetch_generic_data(bs.query_dividend_data, "Dividend", code=code, year=year, yearType=year_type)

    def get_adjust_factor_data(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Fetch adjustment factor data"""
        return fetch_generic_data(bs.query_adjust_factor, "Adjustment Factor", code=code, start_date=start_date,
                                  end_date=end_date)

    def get_performance_express_report(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Fetch performance express report"""
        return fetch_generic_data(bs.query_performance_express_report, "Performance Express Report", code=code,
                                  start_date=start_date, end_date=end_date)

    def get_forecast_report(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Fetch performance forecast report"""
        return fetch_generic_data(bs.query_forecast_report, "Performance Forecast Report", code=code,
                                  start_date=start_date, end_date=end_date)

    def get_stock_industry(self, code: Optional[str] = None, date: Optional[str] = None) -> pd.DataFrame:
        """Fetch stock industry classification"""
        return fetch_generic_data(bs.query_stock_industry, "Industry", code=code, date=date)

    def get_all_stock(self, date: Optional[str] = None) -> pd.DataFrame:
        """Fetch all stock list"""
        return fetch_generic_data(bs.query_all_stock, "All Stock List", day=date)
