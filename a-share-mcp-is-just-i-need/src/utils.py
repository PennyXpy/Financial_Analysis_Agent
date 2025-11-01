# Utility functions, including Baostock login context manager and logging setup
import baostock as bs
import time
import threading
import os
import sys
import logging
import pandas as pd
from contextlib import contextmanager
from typing import List, Optional, Callable, Any
from .data_source_interface import LoginError, DataSourceError, NoDataFoundError


# --- Logging setup ---
def setup_logging(level=logging.INFO):
    """Configure basic logging for the application"""
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    # Optionally mute verbose third-party logs
    # logging.getLogger("mcp").setLevel(logging.WARNING)


# Get logger instance for this module
logger = logging.getLogger(__name__)

# Global lock to prevent concurrent login/logout issues
_baostock_lock = threading.Lock()


# Safe login and logout functions
def safe_login(retries: int = 3, delay: int = 2):
    """Safe login with retries and mutex lock"""
    with _baostock_lock:
        for i in range(1, retries + 1):
            try:
                bs.logout()
            except Exception:
                pass
            lg = bs.login()
            if lg.error_code == "0":
                logger.info("✅ Baostock login successful (safe mode)")
                return
            logger.warning(f"⚠️ Baostock login failed (try {i}/{retries}): {lg.error_msg}")
            time.sleep(delay)
        raise LoginError("❌ Baostock login failed after multiple retries.")


def safe_logout():
    """Safe logout with lock, ignoring non-fatal errors"""
    with _baostock_lock:
        try:
            bs.logout()
            logger.info("✅ Baostock logout successful (safe mode)")
        except Exception as e:
            logger.warning(f"⚠️ Baostock logout error ignored: {e}")


# --- Baostock login context manager ---
@contextmanager
def baostock_login_context():
    """Context manager: suppress stdout + safe login/logout (with lock and retries)"""

    # Suppress stdout during login
    original_stdout_fd = sys.stdout.fileno()
    saved_stdout_fd = os.dup(original_stdout_fd)
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull_fd, original_stdout_fd)
    os.close(devnull_fd)

    # Perform safe login
    try:
        safe_login()
    finally:
        # Restore stdout even if login fails
        os.dup2(saved_stdout_fd, original_stdout_fd)
        os.close(saved_stdout_fd)

    logger.info("Baostock login successful.")
    try:
        # --- Execute API calls within this context ---
        yield
    finally:
        # Suppress stdout during logout
        original_stdout_fd = sys.stdout.fileno()
        saved_stdout_fd = os.dup(original_stdout_fd)
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull_fd, original_stdout_fd)
        os.close(devnull_fd)

        # Perform safe logout
        try:
            safe_logout()
        finally:
            # Restore stdout
            os.dup2(saved_stdout_fd, original_stdout_fd)
            os.close(saved_stdout_fd)

        logger.info("Baostock logout successful.")


# --- Generic data fetching functions ---

def fetch_financial_data(
        bs_query_func: Callable,
        data_type_name: str,
        code: str,
        year: str,
        quarter: int,
        **kwargs
) -> pd.DataFrame:
    """
    Generic financial data fetcher

    Args:
        bs_query_func: Baostock query function
        data_type_name: Name of the data type for logging
        code: Stock code (e.g., "sz.000001")
        year: Year (e.g., "2023")
        quarter: Quarter (1-4)
        **kwargs: Additional parameters

    Returns:
        pandas DataFrame containing financial data

    Raises:
        LoginError: Login failed
        NoDataFoundError: No data found
        DataSourceError: API/data source error
    """
    logger.info(f"Fetching {data_type_name} data for {code}, year={year}, quarter={quarter}")

    try:
        with baostock_login_context():
            rs = bs_query_func(code=code, year=year, quarter=quarter, **kwargs)

            if rs.error_code != '0':
                logger.error(
                    f"Baostock API error ({data_type_name}) for {code}: {rs.error_msg} (code: {rs.error_code})")
                if "no record found" in rs.error_msg.lower() or rs.error_code == '10002':
                    raise NoDataFoundError(
                        f"No {data_type_name} data found for {code}, {year}Q{quarter}. Baostock msg: {rs.error_msg}")
                else:
                    raise DataSourceError(
                        f"Baostock API error fetching {data_type_name} data: {rs.error_msg} (code: {rs.error_code})")

            data_list = []
            while rs.next():
                data_list.append(rs.get_row_data())

            if not data_list:
                logger.warning(f"No {data_type_name} data found for {code}, {year}Q{quarter} (empty result set).")
                raise NoDataFoundError(
                    f"No {data_type_name} data found for {code}, {year}Q{quarter} (empty result set).")

            result_df = pd.DataFrame(data_list, columns=rs.fields)
            logger.info(f"Retrieved {len(result_df)} {data_type_name} records for {code}, {year}Q{quarter}.")
            return result_df

    except (LoginError, NoDataFoundError, DataSourceError, ValueError) as e:
        logger.warning(f"Caught known error fetching {data_type_name} data for {code}: {type(e).__name__}")
        raise e
    except Exception as e:
        logger.exception(f"Unexpected error fetching {data_type_name} data for {code}: {e}")
        raise DataSourceError(f"Unexpected error fetching {data_type_name} data: {e}")


def fetch_index_constituent_data(
        bs_query_func: Callable,
        index_name: str,
        date: Optional[str] = None,
        **kwargs
) -> pd.DataFrame:
    """
    Generic index constituent data fetcher

    Args:
        bs_query_func: Baostock index query function
        index_name: Index name for logging
        date: Optional query date; defaults to latest
        **kwargs: Additional parameters

    Returns:
        pandas DataFrame with index constituents

    Raises:
        LoginError, NoDataFoundError, DataSourceError
    """
    logger.info(f"Fetching {index_name} constituents for date={date or 'latest'}")

    try:
        with baostock_login_context():
            rs = bs_query_func(date=date, **kwargs)

            if rs.error_code != '0':
                logger.error(
                    f"Baostock API error ({index_name} Constituents) for date {date}: {rs.error_msg} (code: {rs.error_code})")
                if "no record found" in rs.error_msg.lower() or rs.error_code == '10002':
                    raise NoDataFoundError(
                        f"No {index_name} constituent data found for date {date}. Baostock msg: {rs.error_msg}")
                else:
                    raise DataSourceError(
                        f"Baostock API error fetching {index_name} constituents: {rs.error_msg} (code: {rs.error_code})")

            data_list = []
            while rs.next():
                data_list.append(rs.get_row_data())

            if not data_list:
                logger.warning(f"No {index_name} constituent data found for date {date} (empty result set).")
                raise NoDataFoundError(f"No {index_name} constituent data found for date {date} (empty result set).")

            result_df = pd.DataFrame(data_list, columns=rs.fields)
            logger.info(f"Retrieved {len(result_df)} {index_name} constituents for date {date or 'latest'}.")
            return result_df

    except (LoginError, NoDataFoundError, DataSourceError, ValueError) as e:
        logger.warning(f"Caught known error fetching {index_name} constituents for date {date}: {type(e).__name__}")
        raise e
    except Exception as e:
        logger.exception(f"Unexpected error fetching {index_name} constituents for date {date}: {e}")
        raise DataSourceError(f"Unexpected error fetching {index_name} constituents for date {date}: {e}")


def fetch_macro_data(
        bs_query_func: Callable,
        data_type_name: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        **kwargs
) -> pd.DataFrame:
    """
    Generic macroeconomic data fetcher
    """
    date_range_log = f"from {start_date or 'default'} to {end_date or 'default'}"
    kwargs_log = f", extra_args={kwargs}" if kwargs else ""
    logger.info(f"Fetching {data_type_name} data {date_range_log}{kwargs_log}")

    try:
        with baostock_login_context():
            rs = bs_query_func(start_date=start_date, end_date=end_date, **kwargs)

            if rs.error_code != '0':
                logger.error(f"Baostock API error ({data_type_name}): {rs.error_msg} (code: {rs.error_code})")
                if "no record found" in rs.error_msg.lower() or rs.error_code == '10002':
                    raise NoDataFoundError(f"No {data_type_name} data found. Baostock msg: {rs.error_msg}")
                else:
                    raise DataSourceError(
                        f"Baostock API error fetching {data_type_name} data: {rs.error_msg} (code: {rs.error_code})")

            data_list = []
            while rs.next():
                data_list.append(rs.get_row_data())

            if not data_list:
                logger.warning(f"No {data_type_name} data found (empty result set).")
                raise NoDataFoundError(f"No {data_type_name} data found (empty result set).")

            result_df = pd.DataFrame(data_list, columns=rs.fields)
            logger.info(f"Retrieved {len(result_df)} {data_type_name} records.")
            return result_df

    except (LoginError, NoDataFoundError, DataSourceError, ValueError) as e:
        logger.warning(f"Caught known error fetching {data_type_name} data: {type(e).__name__}")
        raise e
    except Exception as e:
        logger.exception(f"Unexpected error fetching {data_type_name} data: {e}")
        raise DataSourceError(f"Unexpected error fetching {data_type_name} data: {e}")


def fetch_generic_data(
        bs_query_func: Callable,
        data_type_name: str,
        **kwargs
) -> pd.DataFrame:
    """
    Generic data fetcher for arbitrary Baostock API calls
    """
    kwargs_log = f" with args: {kwargs}" if kwargs else ""
    logger.info(f"Fetching {data_type_name} data{kwargs_log}")

    try:
        with baostock_login_context():
            rs = bs_query_func(**kwargs)

            if rs.error_code != '0':
                logger.error(f"Baostock API error ({data_type_name}): {rs.error_msg} (code: {rs.error_code})")
                if "no record found" in rs.error_msg.lower() or rs.error_code == '10002':
                    raise NoDataFoundError(f"No {data_type_name} data found. Baostock msg: {rs.error_msg}")
                else:
                    raise DataSourceError(
                        f"Baostock API error fetching {data_type_name} data: {rs.error_msg} (code: {rs.error_code})")

            data_list = []
            while rs.next():
                data_list.append(rs.get_row_data())

            if not data_list:
                logger.warning(f"No {data_type_name} data found (empty result set).")
                raise NoDataFoundError(f"No {data_type_name} data found (empty result set).")

            result_df = pd.DataFrame(data_list, columns=rs.fields)
            logger.info(f"Retrieved {len(result_df)} {data_type_name} records.")
            return result_df

    except (LoginError, NoDataFoundError, DataSourceError, ValueError) as e:
        logger.warning(f"Caught known error fetching {data_type_name} data: {type(e).__name__}")
        raise e
    except Exception as e:
        logger.exception(f"Unexpected error fetching {data_type_name} data: {e}")
        raise DataSourceError(f"Unexpected error fetching {data_type_name} data: {e}")


def format_fields(fields: Optional[List[str]], default_fields: List[str]) -> str:
    """
    Format a list of fields into a comma-separated string for Baostock API

    Args:
        fields: User-requested fields (optional)
        default_fields: Default fields if none specified

    Returns:
        Comma-separated string of fields

    Raises:
        ValueError: If any requested field is not a string
    """
    if fields is None or not fields:
        logger.debug(f"No specific fields requested, using defaults: {default_fields}")
        return ",".join(default_fields)

    if not all(isinstance(f, str) for f in fields):
        raise ValueError("All items in the fields list must be strings.")

    logger.debug(f"Using requested fields: {fields}")
    return ",".join(fields)
