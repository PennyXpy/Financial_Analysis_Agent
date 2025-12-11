# Yahoo Finance data source implementation for US stocks and other markets
import yfinance as yf
import pandas as pd
from typing import List, Optional, Dict
import logging
import threading
import time
from datetime import datetime, timedelta
from .data_source_interface import FinancialDataSource, DataSourceError, NoDataFoundError, LoginError

logger = logging.getLogger(__name__)

# ============================================================================
# 全局限流器 - 防止 Yahoo Finance API 封禁
# ============================================================================
_yahoo_finance_lock = threading.Lock()
_last_request_time = 0
_min_request_interval = 2.0  # 🔥 严格限流：每次请求至少间隔 2 秒
_request_failure_count = 0  # Track consecutive failures for exponential backoff
_max_backoff = 120.0  # Maximum backoff time (2 minutes)
_total_request_count = 0  # 请求计数器（用于调试）

# Cache for various data types (extended cache time)
_info_cache: Dict[str, tuple] = {}  # {code: (data, timestamp)}
_kdata_cache: Dict[str, tuple] = {}  # {cache_key: (data, timestamp)}
_financial_cache: Dict[str, tuple] = {}  # {cache_key: (data, timestamp)}
_cache_ttl = 600  # 10 minutes (extended from 5)


class YahooFinanceDataSource(FinancialDataSource):
    """
    Yahoo Finance data source implementation for US stocks and other markets.
    Uses yfinance library to fetch stock data.
    Includes rate limiting and caching to avoid 429 errors.
    """
    
    @staticmethod
    def _normalize_ticker(code: str) -> str:
        """
        Normalize ticker symbols to the format expected by yfinance.
        - Strips common exchange prefixes like 'NASDAQ:', 'NYSE:', 'AMEX:', 'BATS:' (case-insensitive)
        - Trims whitespace
        - Keeps suffix-based tickers (e.g., 'NVDA.TO') intact
        """
        if not code:
            return code
        code = code.strip()
        prefixes = ["NASDAQ:", "NYSE:", "AMEX:", "BATS:", "NASDAQ-", "NYSE-", "AMEX-", "BATS-"]
        upper = code.upper()
        for p in prefixes:
            if upper.startswith(p):
                return code[len(p):].strip().upper()
        return code.upper()

    @staticmethod
    def _clamp_date_range(start_date: str, end_date: str, max_days: int = 14) -> tuple[str, str]:
        """
        Clamp the requested date range to at most `max_days` days to reduce rate limits.
        This is applied defensively for Yahoo Finance calls.
        """
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.today()
            start_dt = datetime.strptime(start_date, "%Y-%m-%d") if start_date else (end_dt - timedelta(days=max_days))
            if (end_dt - start_dt).days > max_days:
                new_start = end_dt - timedelta(days=max_days)
                logger.info(f"Clamping date range to last {max_days} days: {start_dt.date()} -> {new_start.date()} (end {end_dt.date()})")
                return new_start.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")
            return start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")
        except Exception as e:
            logger.warning(f"Could not clamp date range, keeping original: {e}")
            return start_date, end_date
    
    @staticmethod
    def _rate_limit():
        """
        🔥 严格的全局限流器 - 防止 Yahoo Finance 封禁
        
        策略：
        - 基础间隔：2秒
        - 失败后指数退避：2s → 4s → 8s → 16s → ...
        - 最大退避：120秒
        """
        global _last_request_time, _min_request_interval, _request_failure_count, _max_backoff, _total_request_count
        with _yahoo_finance_lock:
            _total_request_count += 1
            
            # Calculate wait time with exponential backoff on failures
            base_interval = _min_request_interval
            if _request_failure_count > 0:
                backoff_multiplier = min(2 ** _request_failure_count, _max_backoff / base_interval)
                interval = min(base_interval * backoff_multiplier, _max_backoff)
                logger.warning(f"⚠️ [Request #{_total_request_count}] Yahoo Finance rate limit: {interval:.1f}s wait due to {_request_failure_count} consecutive failures")
            else:
                interval = base_interval
                logger.debug(f"⏳ [Request #{_total_request_count}] Normal rate limit: {interval:.1f}s")
            
            elapsed = time.time() - _last_request_time
            if elapsed < interval:
                sleep_time = interval - elapsed
                logger.info(f"⏳ Rate limiting: sleeping {sleep_time:.1f}s (total requests so far: {_total_request_count})")
                time.sleep(sleep_time)
            _last_request_time = time.time()
    
    @staticmethod
    def _record_success():
        """Record successful request to reset backoff"""
        global _request_failure_count, _total_request_count
        if _request_failure_count > 0:
            logger.info(f"✅ [Request #{_total_request_count}] Yahoo Finance request succeeded, resetting failure count from {_request_failure_count}")
            _request_failure_count = 0
        else:
            logger.debug(f"✅ [Request #{_total_request_count}] Yahoo Finance request succeeded")
    
    @staticmethod
    def _record_failure():
        """Record failed request to increase backoff"""
        global _request_failure_count, _total_request_count
        _request_failure_count += 1
        logger.error(f"❌ [Request #{_total_request_count}] Yahoo Finance request failed (consecutive failures: {_request_failure_count})")
    
    @staticmethod
    def _get_cached_info(code: str) -> Optional[pd.DataFrame]:
        """Get cached basic info if available and not expired"""
        global _info_cache, _cache_ttl
        if code in _info_cache:
            data, timestamp = _info_cache[code]
            if time.time() - timestamp < _cache_ttl:
                logger.debug(f"Using cached basic info for {code}")
                return data.copy()
            else:
                del _info_cache[code]
        return None
    
    @staticmethod
    def _cache_info(code: str, data: pd.DataFrame):
        """Cache basic info"""
        global _info_cache
        _info_cache[code] = (data.copy(), time.time())
    
    @staticmethod
    def _get_cached_kdata(cache_key: str) -> Optional[pd.DataFrame]:
        """Get cached K-line data if available and not expired"""
        global _kdata_cache, _cache_ttl
        if cache_key in _kdata_cache:
            data, timestamp = _kdata_cache[cache_key]
            if time.time() - timestamp < _cache_ttl:
                logger.debug(f"Using cached K-data for {cache_key}")
                return data.copy()
            else:
                del _kdata_cache[cache_key]
        return None
    
    @staticmethod
    def _cache_kdata(cache_key: str, data: pd.DataFrame):
        """Cache K-line data"""
        global _kdata_cache
        _kdata_cache[cache_key] = (data.copy(), time.time())
    
    @staticmethod
    def _get_cached_financial(cache_key: str) -> Optional[pd.DataFrame]:
        """Get cached financial data if available and not expired"""
        global _financial_cache, _cache_ttl
        if cache_key in _financial_cache:
            data, timestamp = _financial_cache[cache_key]
            if time.time() - timestamp < _cache_ttl:
                logger.debug(f"Using cached financial data for {cache_key}")
                return data.copy()
            else:
                del _financial_cache[cache_key]
        return None
    
    @staticmethod
    def _cache_financial(cache_key: str, data: pd.DataFrame):
        """Cache financial data"""
        global _financial_cache
        _financial_cache[cache_key] = (data.copy(), time.time())

    def _convert_frequency(self, frequency: str) -> str:
        """Convert frequency format from Baostock to yfinance format"""
        freq_map = {
            'd': '1d',      # Daily
            'w': '1wk',     # Weekly
            'm': '1mo',     # Monthly
            '5': '5m',      # 5 minutes
            '15': '15m',    # 15 minutes
            '30': '30m',    # 30 minutes
            '60': '1h',     # 1 hour
        }
        return freq_map.get(frequency, '1d')

    def _convert_adjust_flag(self, adjust_flag: str) -> bool:
        """Convert adjust flag: '1' or '2' = True (adjusted), '3' = False (unadjusted)"""
        return adjust_flag in ['1', '2']

    def get_historical_k_data(
        self,
        code: str,
        start_date: str,
        end_date: str,
        frequency: str = "d",
        adjust_flag: str = "3",
        fields: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """Get historical K-line data from Yahoo Finance with retry logic and caching"""
        code = self._normalize_ticker(code)
        code = self._normalize_ticker(code)
        start_date, end_date = self._clamp_date_range(start_date, end_date, max_days=14)
        logger.info(f"Fetching K-data for {code} ({start_date} to {end_date}), freq={frequency}, adjust={adjust_flag}")
        
        # Check cache first (use clamped dates to avoid cache explosion)
        cache_key = f"{code}_{start_date}_{end_date}_{frequency}_{adjust_flag}"
        cached_data = self._get_cached_kdata(cache_key)
        if cached_data is not None:
            if fields:
                available_fields = ['date', 'code'] + [f for f in fields if f in cached_data.columns]
                return cached_data[available_fields]
            return cached_data
        
        import time
        max_retries = 2  # 🔥 减少重试次数：从 3 → 2
        base_retry_delay = 5  # 🔥 增加重试延迟：从 3s → 5s
        
        for attempt in range(max_retries):
            try:
                # Enforce rate limiting
                self._rate_limit()
                
                # Convert frequency and adjust flag
                interval = self._convert_frequency(frequency)
                auto_adjust = self._convert_adjust_flag(adjust_flag)
                
                # Fetch data from yfinance
                ticker = yf.Ticker(code)
                df = ticker.history(start=start_date, end=end_date, interval=interval, auto_adjust=auto_adjust)
                
                if df.empty:
                    raise NoDataFoundError(f"No historical data found for {code} in the specified range.")
                
                # Rename columns to match Baostock format
                column_mapping = {
                    'Open': 'open',
                    'High': 'high',
                    'Low': 'low',
                    'Close': 'close',
                    'Volume': 'volume',
                }
                
                # Create result DataFrame
                result_df = pd.DataFrame()
                result_df['date'] = df.index.strftime('%Y-%m-%d')
                result_df['code'] = code
                
                # Map columns
                for yf_col, bs_col in column_mapping.items():
                    if yf_col in df.columns:
                        result_df[bs_col] = df[yf_col].values
                
                # Calculate additional fields
                if 'close' in result_df.columns:
                    # Calculate preclose (previous close)
                    result_df['preclose'] = result_df['close'].shift(1)
                    
                    # Calculate pctChg (percentage change)
                    result_df['pctChg'] = ((result_df['close'] - result_df['preclose']) / result_df['preclose'] * 100).round(2)
                    
                    # Calculate amount (volume * close)
                    if 'volume' in result_df.columns:
                        result_df['amount'] = (result_df['volume'] * result_df['close']).round(2)
                
                # Add default fields
                result_df['adjustflag'] = adjust_flag
                result_df['turn'] = 0.0  # Turnover rate not available from yfinance
                result_df['tradestatus'] = '1'  # Assume trading
                result_df['isST'] = '0'  # Not applicable for US stocks
                
                # Add valuation metrics if available (try to get from ticker info)
                try:
                    info = ticker.info
                    if 'trailingPE' in info and info['trailingPE']:
                        result_df['peTTM'] = info['trailingPE']
                    else:
                        result_df['peTTM'] = None
                    
                    if 'priceToBook' in info and info['priceToBook']:
                        result_df['pbMRQ'] = info['priceToBook']
                    else:
                        result_df['pbMRQ'] = None
                except:
                    result_df['peTTM'] = None
                    result_df['pbMRQ'] = None
                
                result_df['psTTM'] = None
                result_df['pcfNcfTTM'] = None
                
                # Cache the full result before field selection
                self._cache_kdata(cache_key, result_df)
                
                # Select requested fields if specified
                if fields:
                    available_fields = ['date', 'code'] + [f for f in fields if f in result_df.columns]
                    result_df = result_df[available_fields]
                
                # Record success to reset backoff
                self._record_success()
                
                logger.info(f"Retrieved {len(result_df)} records for {code}.")
                return result_df
                
            except Exception as e:
                # Record failure for backoff calculation
                self._record_failure()
                error_str = str(e)
                # Check if it's a rate limit error (429)
                if "429" in error_str or "Too Many Requests" in error_str:
                    if attempt < max_retries - 1:
                        # More aggressive exponential backoff for 429 errors: 6s, 12s, 24s
                        wait_time = base_retry_delay * (2 ** (attempt + 1))
                        logger.warning(f"Rate limit (429) hit for {code} K-data, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"Rate limit error for {code} K-data after {max_retries} attempts")
                        raise DataSourceError(f"Rate limit error fetching K-data for {code}. Please try again later.")
                
                # For other errors, check if it's a "no data" error
                if "No data found" in error_str or "symbol may be delisted" in error_str.lower() or "No price data found" in error_str:
                    raise NoDataFoundError(f"No historical data found for {code}. Error: {e}")
                
                # For other errors on last attempt, raise
                if attempt == max_retries - 1:
                    logger.error(f"Error fetching K-data for {code}: {e}")
                    raise DataSourceError(f"Error fetching K-data for {code}: {e}")
                
                # For other errors, retry with shorter delay
                logger.warning(f"Error fetching K-data for {code} (attempt {attempt + 1}/{max_retries}): {e}")
                time.sleep(base_retry_delay)
        
        # Should not reach here, but just in case
        raise DataSourceError(f"Failed to fetch K-data for {code} after {max_retries} attempts")

    def get_stock_basic_info(self, code: str, fields: Optional[List[str]] = None) -> pd.DataFrame:
        """Get basic stock information from Yahoo Finance with retry logic and caching"""
        code = self._normalize_ticker(code)
        logger.info(f"Fetching basic info for {code}")
        
        # Check cache first
        cached_data = self._get_cached_info(code)
        if cached_data is not None:
            if fields:
                available_fields = [f for f in fields if f in cached_data.columns]
                if available_fields:
                    return cached_data[available_fields]
            return cached_data
        
        max_retries = 2  # 🔥 减少重试次数
        base_retry_delay = 5  # 🔥 增加重试延迟
        
        for attempt in range(max_retries):
            try:
                # Enforce rate limiting
                self._rate_limit()
                
                ticker = yf.Ticker(code)
                info = ticker.info
                
                if not info:
                    raise NoDataFoundError(f"No basic info found for {code}.")
                
                # Create DataFrame with basic info
                basic_info = {
                    'code': code,
                    'code_name': info.get('longName', info.get('shortName', code)),
                    'tradeStatus': '1' if info.get('regularMarketPrice') else '0',
                    'industry': info.get('industry', ''),
                    'sector': info.get('sector', ''),
                    'marketCap': info.get('marketCap', None),
                    'currency': info.get('currency', 'USD'),
                    'exchange': info.get('exchange', ''),
                }
                
                result_df = pd.DataFrame([basic_info])
                
                # Select requested fields if specified
                if fields:
                    available_fields = [f for f in fields if f in result_df.columns]
                    if available_fields:
                        result_df = result_df[available_fields]
                
                logger.info(f"Retrieved basic info for {code}.")
                # Cache the result
                self._cache_info(code, result_df)
                # Record success
                self._record_success()
                return result_df
                
            except Exception as e:
                # Record failure
                self._record_failure()
                error_str = str(e)
                # Check if it's a rate limit error (429)
                if "429" in error_str or "Too Many Requests" in error_str:
                    if attempt < max_retries - 1:
                        # More aggressive exponential backoff for 429 errors: 5s, 10s, 20s
                        wait_time = base_retry_delay * (2 ** (attempt + 1))
                        logger.warning(f"Rate limit (429) hit for {code}, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"Rate limit error for {code} after {max_retries} attempts")
                        raise DataSourceError(f"Rate limit error fetching basic info for {code}. Please try again later.")
                
                # For other errors, check if it's a "no data" error
                if "No data found" in error_str or "symbol may be delisted" in error_str.lower():
                    raise NoDataFoundError(f"No basic info found for {code}. Error: {e}")
                
                # For other errors on last attempt, raise
                if attempt == max_retries - 1:
                    logger.error(f"Error fetching basic info for {code}: {e}")
                    raise DataSourceError(f"Error fetching basic info for {code}: {e}")
                
                # For other errors, retry with shorter delay
                logger.warning(f"Error fetching basic info for {code} (attempt {attempt + 1}/{max_retries}): {e}")
                time.sleep(base_retry_delay)
        
        # Should not reach here, but just in case
        raise DataSourceError(f"Failed to fetch basic info for {code} after {max_retries} attempts")

    def get_trade_dates(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        """Get trading dates (not directly available from yfinance, return empty DataFrame)"""
        logger.warning("get_trade_dates not implemented for Yahoo Finance data source")
        return pd.DataFrame(columns=['date', 'is_trading'])

    def get_all_stock(self, date: Optional[str] = None) -> pd.DataFrame:
        """Get all stocks (not directly available from yfinance, return empty DataFrame)"""
        logger.warning("get_all_stock not implemented for Yahoo Finance data source")
        return pd.DataFrame(columns=['code', 'code_name', 'tradeStatus'])

    def get_deposit_rate_data(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        """Get deposit rate data (not available from yfinance, return empty DataFrame)"""
        logger.warning("get_deposit_rate_data not implemented for Yahoo Finance data source")
        return pd.DataFrame()

    def get_loan_rate_data(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        """Get loan rate data (not available from yfinance, return empty DataFrame)"""
        logger.warning("get_loan_rate_data not implemented for Yahoo Finance data source")
        return pd.DataFrame()

    def get_required_reserve_ratio_data(self, start_date: Optional[str] = None, end_date: Optional[str] = None, year_type: str = '0') -> pd.DataFrame:
        """Get required reserve ratio data (not available from yfinance, return empty DataFrame)"""
        logger.warning("get_required_reserve_ratio_data not implemented for Yahoo Finance data source")
        return pd.DataFrame()

    def get_money_supply_data_month(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        """Get monthly money supply data (not available from yfinance, return empty DataFrame)"""
        logger.warning("get_money_supply_data_month not implemented for Yahoo Finance data source")
        return pd.DataFrame()

    def get_money_supply_data_year(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        """Get yearly money supply data (not available from yfinance, return empty DataFrame)"""
        logger.warning("get_money_supply_data_year not implemented for Yahoo Finance data source")
        return pd.DataFrame()

    # Financial report methods - use yfinance financial statements
    def get_profit_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        """Get profit data (income statement) from Yahoo Finance with caching"""
        code = self._normalize_ticker(code)
        logger.info(f"Fetching profit data for {code}, {year}Q{quarter}")
        
        # Check cache first
        cache_key = f"profit_{code}_{year}_{quarter}"
        cached_data = self._get_cached_financial(cache_key)
        if cached_data is not None:
            return cached_data
        
        try:
            import time
            max_retries = 3
            retry_delay = 5  # Increased delay for rate limiting
            
            for attempt in range(max_retries):
                try:
                    # Enforce rate limiting
                    self._rate_limit()
                    
                    ticker = yf.Ticker(code)
                    financials = ticker.financials
                    
                    if financials is None or financials.empty:
                        logger.warning(f"No financial data available for {code}")
                        # Try to get from quarterly financials
                        try:
                            financials = ticker.quarterly_financials
                            if financials is None or financials.empty:
                                return pd.DataFrame()
                        except:
                            return pd.DataFrame()
                    
                    # Convert to long format to match Baostock format
                    # financials has dates as columns, metrics as rows
                    result_df = financials.T.reset_index()
                    # Rename the index column to 'date'
                    if len(result_df.columns) > 0:
                        result_df.rename(columns={result_df.columns[0]: 'date'}, inplace=True)
                    result_df['code'] = code
                    
                    # Convert date column to string for filtering
                    if 'date' in result_df.columns:
                        result_df['date'] = result_df['date'].astype(str)
                        # Filter by year if specified
                        if year:
                            result_df = result_df[result_df['date'].str.startswith(str(year))]
                    
                    logger.info(f"Retrieved profit data for {code}, shape: {result_df.shape}")
                    # Cache the result
                    self._cache_financial(cache_key, result_df)
                    return result_df
                    
                except Exception as e:
                    error_str = str(e)
                    if "429" in error_str or "Too Many Requests" in error_str:
                        if attempt < max_retries - 1:
                            wait_time = retry_delay * (attempt + 1) * 2  # Longer wait for rate limits
                            logger.warning(f"Rate limit hit for {code} profit data, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                            time.sleep(wait_time)
                            continue
                    # For JSON decode errors (also often rate limit related)
                    if "Expecting value" in error_str or "JSONDecodeError" in error_str:
                        if attempt < max_retries - 1:
                            wait_time = retry_delay * (attempt + 1) * 2
                            logger.warning(f"JSON decode error for {code} profit data (likely rate limit), retrying in {wait_time}s")
                            time.sleep(wait_time)
                            continue
                    if attempt == max_retries - 1:
                        logger.error(f"Error fetching profit data for {code}: {e}")
                        return pd.DataFrame()
                    time.sleep(retry_delay)
            
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"Error fetching profit data for {code}: {e}")
            return pd.DataFrame()

    def get_operation_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        """Get operation data - calculate from financial statements"""
        logger.info(f"Fetching operation data for {code}, {year}Q{quarter}")
        # Operation metrics can be calculated from financial statements
        # For now, return empty as it requires complex calculations
        return pd.DataFrame()

    def get_growth_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        """Get growth data - calculate from financial statements"""
        logger.info(f"Fetching growth data for {code}, {year}Q{quarter}")
        # Growth metrics can be calculated from financial statements
        # For now, return empty as it requires historical comparison
        return pd.DataFrame()

    def get_balance_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        """Get balance sheet data from Yahoo Finance with caching"""
        code = self._normalize_ticker(code)
        logger.info(f"Fetching balance sheet data for {code}, {year}Q{quarter}")
        
        # Check cache first
        cache_key = f"balance_{code}_{year}_{quarter}"
        cached_data = self._get_cached_financial(cache_key)
        if cached_data is not None:
            return cached_data
        
        try:
            import time
            max_retries = 3
            retry_delay = 5  # Increased delay
            
            for attempt in range(max_retries):
                try:
                    # Enforce rate limiting
                    self._rate_limit()
                    
                    ticker = yf.Ticker(code)
                    balance_sheet = ticker.balance_sheet
                    
                    if balance_sheet is None or balance_sheet.empty:
                        logger.warning(f"No balance sheet data available for {code}")
                        # Try quarterly
                        try:
                            balance_sheet = ticker.quarterly_balance_sheet
                            if balance_sheet is None or balance_sheet.empty:
                                return pd.DataFrame()
                        except:
                            return pd.DataFrame()
                    
                    # Convert to long format
                    result_df = balance_sheet.T.reset_index()
                    if len(result_df.columns) > 0:
                        result_df.rename(columns={result_df.columns[0]: 'date'}, inplace=True)
                    result_df['code'] = code
                    
                    # Filter by year if specified
                    if 'date' in result_df.columns:
                        result_df['date'] = result_df['date'].astype(str)
                        if year:
                            result_df = result_df[result_df['date'].str.startswith(str(year))]
                    
                    logger.info(f"Retrieved balance sheet data for {code}, shape: {result_df.shape}")
                    # Cache the result
                    self._cache_financial(cache_key, result_df)
                    return result_df
                    
                except Exception as e:
                    error_str = str(e)
                    if "429" in error_str or "Too Many Requests" in error_str:
                        if attempt < max_retries - 1:
                            wait_time = retry_delay * (attempt + 1) * 2
                            logger.warning(f"Rate limit hit for {code} balance sheet, retrying in {wait_time}s")
                            time.sleep(wait_time)
                            continue
                    if "Expecting value" in error_str or "JSONDecodeError" in error_str:
                        if attempt < max_retries - 1:
                            wait_time = retry_delay * (attempt + 1) * 2
                            logger.warning(f"JSON decode error for {code} balance sheet, retrying in {wait_time}s")
                            time.sleep(wait_time)
                            continue
                    if attempt == max_retries - 1:
                        logger.error(f"Error fetching balance sheet for {code}: {e}")
                        return pd.DataFrame()
                    time.sleep(retry_delay)
            
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"Error fetching balance sheet for {code}: {e}")
            return pd.DataFrame()

    def get_cash_flow_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        """Get cash flow data from Yahoo Finance with caching"""
        code = self._normalize_ticker(code)
        logger.info(f"Fetching cash flow data for {code}, {year}Q{quarter}")
        
        # Check cache first
        cache_key = f"cashflow_{code}_{year}_{quarter}"
        cached_data = self._get_cached_financial(cache_key)
        if cached_data is not None:
            return cached_data
        
        try:
            import time
            max_retries = 3
            retry_delay = 5  # Increased delay
            
            for attempt in range(max_retries):
                try:
                    # Enforce rate limiting
                    self._rate_limit()
                    
                    ticker = yf.Ticker(code)
                    cashflow = ticker.cashflow
                    
                    if cashflow is None or cashflow.empty:
                        logger.warning(f"No cash flow data available for {code}")
                        # Try quarterly
                        try:
                            cashflow = ticker.quarterly_cashflow
                            if cashflow is None or cashflow.empty:
                                return pd.DataFrame()
                        except:
                            return pd.DataFrame()
                    
                    # Convert to long format
                    result_df = cashflow.T.reset_index()
                    if len(result_df.columns) > 0:
                        result_df.rename(columns={result_df.columns[0]: 'date'}, inplace=True)
                    result_df['code'] = code
                    
                    # Filter by year if specified
                    if 'date' in result_df.columns:
                        result_df['date'] = result_df['date'].astype(str)
                        if year:
                            result_df = result_df[result_df['date'].str.startswith(str(year))]
                    
                    logger.info(f"Retrieved cash flow data for {code}, shape: {result_df.shape}")
                    # Cache the result
                    self._cache_financial(cache_key, result_df)
                    return result_df
                    
                except Exception as e:
                    error_str = str(e)
                    if "429" in error_str or "Too Many Requests" in error_str:
                        if attempt < max_retries - 1:
                            wait_time = retry_delay * (attempt + 1) * 2
                            logger.warning(f"Rate limit hit for {code} cash flow, retrying in {wait_time}s")
                            time.sleep(wait_time)
                            continue
                    if "Expecting value" in error_str or "JSONDecodeError" in error_str:
                        if attempt < max_retries - 1:
                            wait_time = retry_delay * (attempt + 1) * 2
                            logger.warning(f"JSON decode error for {code} cash flow, retrying in {wait_time}s")
                            time.sleep(wait_time)
                            continue
                    if attempt == max_retries - 1:
                        logger.error(f"Error fetching cash flow for {code}: {e}")
                        return pd.DataFrame()
                    time.sleep(retry_delay)
            
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"Error fetching cash flow for {code}: {e}")
            return pd.DataFrame()

    def get_dupont_data(self, code: str, year: str, quarter: int) -> pd.DataFrame:
        """Get DuPont analysis data (not available from yfinance)"""
        logger.warning(f"get_dupont_data not fully implemented for Yahoo Finance data source for {code}")
        return pd.DataFrame()

    def get_dividend_data(self, code: str, year: str, year_type: str = "report") -> pd.DataFrame:
        """Get dividend data from Yahoo Finance"""
        try:
            code = self._normalize_ticker(code)
            ticker = yf.Ticker(code)
            dividends = ticker.dividends
            
            if dividends.empty:
                return pd.DataFrame(columns=['date', 'dividend'])
            
            result_df = pd.DataFrame({
                'date': dividends.index.strftime('%Y-%m-%d'),
                'dividend': dividends.values,
                'code': code
            })
            
            # Filter by year if specified
            if year:
                result_df = result_df[result_df['date'].str.startswith(year)]
            
            return result_df
            
        except Exception as e:
            logger.error(f"Error fetching dividend data for {code}: {e}")
            return pd.DataFrame(columns=['date', 'dividend', 'code'])

    def crawl_news(self, query: str, top_k: int = 10) -> str:
        """Crawl news using Yahoo Finance news"""
        try:
            # Try to extract stock symbol from query
            import re
            symbol_match = re.search(r'\b([A-Z]{1,5})\b', query.upper())
            if symbol_match:
                symbol = symbol_match.group(1)
                ticker = yf.Ticker(symbol)
                news = ticker.news
                
                if news:
                    output = f"Found {len(news[:top_k])} news articles for {symbol}:\n\n"
                    for i, article in enumerate(news[:top_k], 1):
                        output += f"{i}. {article.get('title', 'No title')}\n"
                        output += f"   Source: {article.get('publisher', 'Unknown')}\n"
                        output += f"   Link: {article.get('link', 'No link')}\n\n"
                    return output
            
            return "No news found. Please provide a valid stock symbol."
            
        except Exception as e:
            logger.error(f"Error crawling news: {e}")
            return f"Error crawling news: {str(e)}"

