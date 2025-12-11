"""
Stock Market Data Tools for MCP Server
Provides historical K-line, basic info, dividend, and adjust factor data.
"""

import logging
from typing import List, Optional, Callable, Any

from mcp.server.fastmcp import FastMCP
from src.data_source_interface import FinancialDataSource, NoDataFoundError, LoginError, DataSourceError
from src.formatting.markdown_formatter import format_df_to_markdown

logger = logging.getLogger(__name__)


def safe_data_fetch(
        func_name: str,
        data_source_func: Callable,
        *args,
        **kwargs
) -> str:
    """
    Safe data fetch function to uniformly handle all exceptions and errors.

    Args:
        func_name: Function name for logging purposes.
        data_source_func: Data source function.
        *args: Positional arguments for the data source function.
        **kwargs: Keyword arguments for the data source function.

    Returns:
        Markdown-formatted data table or error message.
    """
    try:
        df = data_source_func(*args, **kwargs)
        logger.info(f"Successfully retrieved data for {func_name}, formatting to Markdown.")
        return format_df_to_markdown(df)

    except NoDataFoundError as e:
        logger.warning(f"NoDataFoundError for {func_name}: {e}")
        return f"Error: {e}"
    except LoginError as e:
        logger.error(f"LoginError for {func_name}: {e}")
        return f"Error: Could not connect to data source. {e}"
    except DataSourceError as e:
        logger.error(f"DataSourceError for {func_name}: {e}")
        return f"Error: An error occurred while fetching data. {e}"
    except ValueError as e:
        logger.warning(f"ValueError processing request for {func_name}: {e}")
        return f"Error: Invalid input parameter. {e}"
    except Exception as e:
        logger.exception(f"Unexpected Exception processing {func_name}: {e}")
        return f"Error: An unexpected error occurred: {e}"


def register_stock_market_tools(app: FastMCP, active_data_source: FinancialDataSource):
    """
    Register stock market data tools with the MCP application.

    Args:
        app: FastMCP application instance.
        active_data_source: Active financial data source.
    """

    @app.tool()
    def get_historical_k_data(
            code: str,
            start_date: str,
            end_date: str,
            frequency: str = "d",
            adjust_flag: str = "3",
            fields: Optional[List[str]] = None,
    ) -> str:
        """
        Fetch historical OHLCV data (K-line) for Chinese A-shares.

        Args:
            code: Stock code in Baostock format (e.g., 'sh.600000', 'sz.000001').
            start_date: Start date in 'YYYY-MM-DD' format.
            end_date: End date in 'YYYY-MM-DD' format.
            frequency: Data frequency ('d'=daily, 'w'=weekly, 'm'=monthly, '5'=5min, '15'=15min, '30'=30min, '60'=60min).
            adjust_flag: Adjustment flag ('1'=forward, '2'=backward, '3'=none).
            fields: Optional list of specific fields; defaults to standard OHLCV fields.

        Returns:
            Markdown table of K-line data or error message.
        """
        logger.info(
            f"Tool 'get_historical_k_data' called for {code} ({start_date}-{end_date}, freq={frequency}, adj={adjust_flag}, fields={fields})")

        valid_freqs = ['d', 'w', 'm', '5', '15', '30', '60']
        valid_adjusts = ['1', '2', '3']
        if frequency not in valid_freqs:
            return f"Error: Invalid frequency '{frequency}'. Valid options: {valid_freqs}"
        if adjust_flag not in valid_adjusts:
            return f"Error: Invalid adjust_flag '{adjust_flag}'. Valid options: {valid_adjusts}"

        return safe_data_fetch(
            "get_historical_k_data",
            active_data_source.get_historical_k_data,
            code=code,
            start_date=start_date,
            end_date=end_date,
            frequency=frequency,
            adjust_flag=adjust_flag,
            fields=fields,
        )

    @app.tool()
    def get_stock_basic_info(code: str, fields: Optional[List[str]] = None) -> str:
        """
        Fetch basic information of a Chinese A-share stock.

        Args:
            code: Stock code in Baostock format.
            fields: Optional list of specific columns; defaults to all available.

        Returns:
            Markdown table of stock info or error message.
        """
        logger.info(f"Tool 'get_stock_basic_info' called for {code} (fields={fields})")
        return safe_data_fetch(
            "get_stock_basic_info",
            active_data_source.get_stock_basic_info,
            code=code,
            fields=fields,
        )

    @app.tool()
    def get_dividend_data(code: str, year: str, year_type: str = "report") -> str:
        """
        Fetch dividend data for a stock for a given year.

        Args:
            code: Stock code in Baostock format.
            year: Year as a 4-digit string (e.g., '2023').
            year_type: 'report'=announcement year, 'operate'=ex-dividend year.

        Returns:
            Markdown table of dividend data or error message.
        """
        logger.info(f"Tool 'get_dividend_data' called for {code}, year={year}, year_type={year_type}")
        if year_type not in ['report', 'operate']:
            return "Error: Invalid year_type. Valid options: 'report', 'operate'"
        if not year.isdigit() or len(year) != 4:
            return "Error: Invalid year format. Provide a 4-digit year."

        return safe_data_fetch(
            "get_dividend_data",
            active_data_source.get_dividend_data,
            code=code,
            year=year,
            year_type=year_type,
        )

    @app.tool()
    def get_adjust_factor_data(code: str, start_date: str, end_date: str) -> str:
        """
        Fetch adjustment factors for a stock over a date range.

        Args:
            code: Stock code in Baostock format.
            start_date: Start date in 'YYYY-MM-DD' format.
            end_date: End date in 'YYYY-MM-DD' format.

        Returns:
            Markdown table of adjust factors or error message.
        """
        logger.info(f"Tool 'get_adjust_factor_data' called for {code} ({start_date} to {end_date})")
        return safe_data_fetch(
            "get_adjust_factor_data",
            active_data_source.get_adjust_factor_data,
            code=code,
            start_date=start_date,
            end_date=end_date,
        )
