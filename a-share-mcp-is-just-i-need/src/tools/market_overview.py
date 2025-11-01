"""
Market overview tools for the MCP server.
Includes tools to fetch trading days and all stock data.
"""
import logging
from typing import Optional

from mcp.server.fastmcp import FastMCP
from src.data_source_interface import FinancialDataSource, NoDataFoundError, LoginError, DataSourceError
from src.formatting.markdown_formatter import format_df_to_markdown

logger = logging.getLogger(__name__)


def safe_market_data_fetch(
        func_name: str,
        data_source_func,
        data_type: str,
        **kwargs
) -> str:
    """
    Safe market data fetch function that handles all exceptions and errors consistently.

    Args:
        func_name: Name of the function (for logging purposes).
        data_source_func: Data source function to call.
        data_type: Description of the data type.
        **kwargs: Keyword arguments to pass to the data source function.

    Returns:
        Markdown table of the data or an error message.
    """
    try:
        df = data_source_func(**kwargs)
        logger.info(f"Successfully retrieved {data_type} data.")
        return format_df_to_markdown(df)

    except NoDataFoundError as e:
        logger.warning(f"NoDataFoundError: {e}")
        return f"Error: {e}"
    except LoginError as e:
        logger.error(f"LoginError: {e}")
        return f"Error: Could not connect to data source. {e}"
    except DataSourceError as e:
        logger.error(f"DataSourceError: {e}")
        return f"Error: An error occurred while fetching data. {e}"
    except ValueError as e:
        logger.warning(f"ValueError: {e}")
        return f"Error: Invalid input parameter. {e}"
    except Exception as e:
        logger.exception(f"Unexpected Exception processing {func_name}: {e}")
        return f"Error: An unexpected error occurred: {e}"


def register_market_overview_tools(app: FastMCP, active_data_source: FinancialDataSource):
    """
    Register market overview tools to the MCP application.

    Args:
        app: FastMCP application instance.
        active_data_source: Active financial data source.
    """

    @app.tool()
    def get_trade_dates(start_date: Optional[str] = None, end_date: Optional[str] = None) -> str:
        """
        Fetch trading day information for a specified range.

        Args:
            start_date: Optional start date in 'YYYY-MM-DD' format. Defaults to '2015-01-01' if None.
            end_date: Optional end date in 'YYYY-MM-DD' format. Defaults to today if None.

        Returns:
            Markdown table indicating whether each date is a trading day (1) or not (0).
        """
        logger.info(
            f"Tool 'get_trade_dates' called for range {start_date or 'default'} to {end_date or 'default'}")

        return safe_market_data_fetch(
            "get_trade_dates",
            active_data_source.get_trade_dates,
            "Trading Days",
            start_date=start_date,
            end_date=end_date
        )

    @app.tool()
    def get_all_stock(date: Optional[str] = None) -> str:
        """
        Fetch the list of all stocks (A-shares and indices) and their trading status for a specified date.

        Args:
            date: Optional date in 'YYYY-MM-DD' format. Defaults to today if None.

        Returns:
            Markdown table listing stock codes, names, and trading status (1=trading, 0=suspended).
        """
        logger.info(
            f"Tool 'get_all_stock' called for date={date or 'default'}")

        return safe_market_data_fetch(
            "get_all_stock",
            active_data_source.get_all_stock,
            "All Stocks",
            date=date
        )
