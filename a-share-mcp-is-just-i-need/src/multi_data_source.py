# Multi-data source adapter that automatically selects the appropriate data source
import logging
import re
import threading
from typing import Optional, List
import pandas as pd
from .data_source_interface import FinancialDataSource, DataSourceError, NoDataFoundError, LoginError
from .baostock_data_source import BaostockDataSource
from .yahoo_finance_data_source import YahooFinanceDataSource
from .polygon_data_source import PolygonDataSource
from .finnhub_data_source import FinnhubDataSource

logger = logging.getLogger(__name__)

# Global singleton instance with thread-safe lock
_multi_data_source_instance = None
_multi_data_source_lock = threading.Lock()


class MultiDataSource(FinancialDataSource):
    """
    Multi-data source adapter that automatically selects the appropriate data source
    based on stock code format:
    - A-share stocks (sh.xxxxxx or sz.xxxxxx) -> BaostockDataSource
    - US stocks (AAPL, TSLA, etc.) -> YahooFinanceDataSource
    
    This class implements the thread-safe Singleton pattern.
    """

    def __new__(cls):
        """Thread-safe singleton pattern with double-checked locking"""
        global _multi_data_source_instance, _multi_data_source_lock
        
        # Fast path: check without lock
        if _multi_data_source_instance is not None:
            logger.debug("♻️ [Fast path] Reusing EXISTING MultiDataSource singleton instance")
            return _multi_data_source_instance
        
        # Slow path: acquire lock and double-check
        with _multi_data_source_lock:
            if _multi_data_source_instance is None:
                logger.info("🔧 [Locked] Creating NEW MultiDataSource singleton instance")
                _multi_data_source_instance = super(MultiDataSource, cls).__new__(cls)
                _multi_data_source_instance._initialized = False
            else:
                logger.info("♻️ [Locked] Another thread created MultiDataSource, reusing it")
            return _multi_data_source_instance

    def __init__(self):
        """Initialize both data sources (only once due to singleton)"""
        global _multi_data_source_lock
        
        # Fast path: skip if already initialized
        if getattr(self, '_initialized', False):
            logger.debug("♻️ MultiDataSource already initialized, skipping")
            return
        
        # Slow path: acquire lock and initialize
        with _multi_data_source_lock:
            # Double-check after acquiring lock
            if getattr(self, '_initialized', False):
                logger.debug("♻️ Another thread initialized MultiDataSource, skipping")
                return
            
            logger.info("🚀 [Locked] Initializing MultiDataSource data sources...")
            self.baostock = BaostockDataSource()
            self.yahoo = YahooFinanceDataSource()
            self.finnhub = FinnhubDataSource()
            self.polygon = PolygonDataSource()
            self._initialized = True
            logger.info("✅ MultiDataSource initialized: Baostock (A), Polygon (US market), Finnhub (US financials/news), Yahoo (fallback)")

    def _is_a_share_code(self, code: str) -> bool:
        """Check if code is A-share format (sh.xxxxxx or sz.xxxxxx)"""
        return code.startswith('sh.') or code.startswith('sz.')

    def _is_us_stock_code(self, code: str) -> bool:
        """Check if code is US stock format (1-5 uppercase letters)"""
        # US stock codes are typically 1-5 uppercase letters
        pattern = r'^[A-Z]{1,5}$'
        return bool(re.match(pattern, code.upper()))

    def _get_data_source(self, code: str) -> FinancialDataSource:
        """Get the appropriate data source based on stock code"""
        if self._is_a_share_code(code):
            logger.debug(f"Using Baostock data source for A-share code: {code}")
            return self.baostock
        # US / unknown formats handled per-method below
        logger.debug(f"Non A-share code detected: {code}, method-level routing will decide.")
        return self.yahoo

    def get_historical_k_data(
        self,
        code: str,
        start_date: str,
        end_date: str,
        frequency: str = "d",
        adjust_flag: str = "3",
        fields: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """Get historical K-line data from appropriate data source"""
        # A-share -> Baostock
        if self._is_a_share_code(code):
            return self.baostock.get_historical_k_data(code, start_date, end_date, frequency, adjust_flag, fields)

        # US -> Polygon primary, Yahoo fallback
        if self._is_us_stock_code(code):
            try:
                return self.polygon.get_historical_k_data(code, start_date, end_date, frequency, adjust_flag, fields)
            except (NoDataFoundError, DataSourceError) as e:
                logger.warning(f"Polygon K-line failed for {code}: {e}, falling back to Finnhub.")
                try:
                    return self.finnhub.get_historical_k_data(code, start_date, end_date, frequency, adjust_flag, fields)
                except Exception as e2:
                    logger.warning(f"Finnhub K-line failed for {code}: {e2}, falling back to Yahoo.")
                    return self.yahoo.get_historical_k_data(code, start_date, end_date, frequency, adjust_flag, fields)

        # Unknown -> Yahoo
        return self.yahoo.get_historical_k_data(code, start_date, end_date, frequency, adjust_flag, fields)

    def get_stock_basic_info(self, code: str, fields: Optional[List[str]] = None) -> pd.DataFrame:
        """Get basic stock info from appropriate data source"""
        if self._is_a_share_code(code):
            return self.baostock.get_stock_basic_info(code, fields)
        if self._is_us_stock_code(code):
            try:
                return self.polygon.get_stock_basic_info(code, fields)
            except (NoDataFoundError, DataSourceError) as e:
                logger.warning(f"Polygon basic info failed for {code}: {e}, falling back to Finnhub.")
                try:
                    return self.finnhub.get_stock_basic_info(code, fields)
                except Exception as e2:
                    logger.warning(f"Finnhub basic info failed for {code}: {e2}, falling back to Yahoo.")
                    return self.yahoo.get_stock_basic_info(code, fields)
        return self.yahoo.get_stock_basic_info(code, fields)

    def get_trade_dates(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        """Get trading dates (only available from Baostock for A-shares)"""
        # Trading dates are mainly relevant for A-shares
        return self.baostock.get_trade_dates(start_date, end_date)

    def get_all_stock(self, date: Optional[str] = None) -> pd.DataFrame:
        """Get all stocks (only available from Baostock for A-shares)"""
        return self.baostock.get_all_stock(date)

    def get_stock_industry(self, code: Optional[str] = None, date: Optional[str] = None) -> pd.DataFrame:
        """Get stock industry classification data"""
        if code and self._is_us_stock_code(code):
            # For US stocks, get industry info from basic info
            try:
                basic_info = self.yahoo.get_stock_basic_info(code)
                if not basic_info.empty and 'industry' in basic_info.columns:
                    # Return in similar format to Baostock
                    industry_df = pd.DataFrame([{
                        'code': code,
                        'code_name': basic_info.iloc[0].get('code_name', code),
                        'industry': basic_info.iloc[0].get('industry', ''),
                        'industryClassification': basic_info.iloc[0].get('sector', ''),
                    }])
                    return industry_df
            except:
                pass
            return pd.DataFrame()
        else:
            # For A-shares, use Baostock
            return self.baostock.get_stock_industry(code, date)

    def get_deposit_rate_data(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        """Get deposit rate data (only available from Baostock for China)"""
        return self.baostock.get_deposit_rate_data(start_date, end_date)

    def get_loan_rate_data(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        """Get loan rate data (only available from Baostock for China)"""
        return self.baostock.get_loan_rate_data(start_date, end_date)

    def get_required_reserve_ratio_data(self, start_date: Optional[str] = None, end_date: Optional[str] = None, year_type: str = '0') -> pd.DataFrame:
        """Get required reserve ratio data (only available from Baostock for China)"""
        return self.baostock.get_required_reserve_ratio_data(start_date, end_date, year_type)

    def get_money_supply_data_month(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        """Get monthly money supply data (only available from Baostock for China)"""
        return self.baostock.get_money_supply_data_month(start_date, end_date)

    def get_money_supply_data_year(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        """Get yearly money supply data (only available from Baostock for China)"""
        return self.baostock.get_money_supply_data_year(start_date, end_date)

    # Financial report methods - delegate to appropriate source
    def get_profit_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        """Get profit data from appropriate data source"""
        if self._is_a_share_code(code):
            return self.baostock.get_profit_data(code, year, quarter)
        # US: Finnhub primary, Yahoo fallback
        try:
            return self.finnhub.get_profit_data(code, year, quarter)
        except Exception as e:
            logger.warning(f"Finnhub profit failed for {code}: {e}, falling back to Yahoo.")
            return self.yahoo.get_profit_data(code, year, quarter)

    def get_operation_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        """Get operation data from appropriate data source"""
        if self._is_a_share_code(code):
            return self.baostock.get_operation_data(code, year, quarter)
        return self.finnhub.get_operation_data(code, year, quarter)

    def get_growth_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        """Get growth data from appropriate data source"""
        if self._is_a_share_code(code):
            return self.baostock.get_growth_data(code, year, quarter)
        try:
            return self.finnhub.get_growth_data(code, year, quarter)
        except Exception:
            return pd.DataFrame()

    def get_balance_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        """Get balance sheet data from appropriate data source"""
        if self._is_a_share_code(code):
            return self.baostock.get_balance_data(code, year, quarter)
        try:
            return self.finnhub.get_balance_data(code, year, quarter)
        except Exception as e:
            logger.warning(f"Finnhub balance failed for {code}: {e}, falling back to Yahoo.")
            return self.yahoo.get_balance_data(code, year, quarter)

    def get_cash_flow_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        """Get cash flow data from appropriate data source"""
        if self._is_a_share_code(code):
            return self.baostock.get_cash_flow_data(code, year, quarter)
        try:
            return self.finnhub.get_cash_flow_data(code, year, quarter)
        except Exception as e:
            logger.warning(f"Finnhub cash flow failed for {code}: {e}, falling back to Yahoo.")
            return self.yahoo.get_cash_flow_data(code, year, quarter)

    def get_dupont_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        """Get DuPont analysis data from appropriate data source"""
        if self._is_a_share_code(code):
            return self.baostock.get_dupont_data(code, year, quarter)
        try:
            return self.finnhub.get_dupont_data(code, year, quarter)
        except Exception:
            return pd.DataFrame()

    def get_dividend_data(self, code: str, year: str, year_type: str = "report") -> pd.DataFrame:
        """Get dividend data from appropriate data source"""
        if self._is_a_share_code(code):
            return self.baostock.get_dividend_data(code, year, year_type)
        if self._is_us_stock_code(code):
            try:
                return self.polygon.get_dividend_data(code, year, year_type)
            except (NoDataFoundError, DataSourceError) as e:
                logger.warning(f"Polygon dividend failed for {code}: {e}, falling back to Finnhub.")
                try:
                    return self.finnhub.get_dividend_data(code, year, year_type)
                except Exception as e2:
                    logger.warning(f"Finnhub dividend failed for {code}: {e2}, falling back to Yahoo.")
                    return self.yahoo.get_dividend_data(code, year, year_type)
        return self.yahoo.get_dividend_data(code, year, year_type)

    def crawl_news(self, query: str, top_k: int = 10) -> str:
        """Crawl news - try both data sources"""
        # Try Finnhub first for US
        try:
            result = self.finnhub.crawl_news(query, top_k)
            if result and "No news found" not in result:
                return result
        except Exception:
            pass
        # Fall back to Yahoo
        try:
            result = self.yahoo.crawl_news(query, top_k)
            if result and "No news found" not in result:
                return result
        except Exception:
            pass
        # Fall back to Baostock
        if hasattr(self.baostock, 'crawl_news'):
            return self.baostock.crawl_news(query, top_k)
        return "No news found."

