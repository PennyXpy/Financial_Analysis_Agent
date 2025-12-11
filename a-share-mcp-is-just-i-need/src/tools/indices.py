"""
Index-related tools for the MCP server.
Includes tools to fetch index constituent stocks.
"""
import logging
from typing import Optional

from mcp.server.fastmcp import FastMCP
from src.data_source_interface import FinancialDataSource
from src.tools.base import call_index_constituent_tool

logger = logging.getLogger(__name__)


def register_index_tools(app: FastMCP, active_data_source: FinancialDataSource):
    """
    Register index-related tools to the MCP application.

    Args:
        app: FastMCP application instance.
        active_data_source: Active financial data source.
    """

    @app.tool()
    def get_stock_industry(code: Optional[str] = None, date: Optional[str] = None) -> str:
        """
        Fetch industry classification data for a specified stock, or for all stocks on a given date.

        Args:
            code: Optional stock code (e.g., 'sh.600000'). If None, fetch data for all stocks.
            date: Optional date in 'YYYY-MM-DD' format. If None, use the latest available date.

        Returns:
            Markdown table containing industry classification data or an error message.
        """
        log_msg = f"Tool 'get_stock_industry' called for code={code or 'all'}, date={date or 'latest'}"
        logger.info(log_msg)
        try:
            df = active_data_source.get_stock_industry(code=code, date=date)
            logger.info(f"Successfully retrieved industry data for {code or 'all'}, {date or 'latest'}.")
            from src.formatting.markdown_formatter import format_df_to_markdown
            return format_df_to_markdown(df)

        except Exception as e:
            logger.exception(f"Exception processing get_stock_industry: {e}")
            return f"Error: An unexpected error occurred: {e}"

    @app.tool()
    def get_sz50_stocks(date: Optional[str] = None) -> str:
        """
        Fetch the constituent stocks of the SZ50 index on a specified date.

        Args:
            date: Optional date in 'YYYY-MM-DD' format. If None, use the latest available date.

        Returns:
            Markdown table containing SZ50 constituent stocks or an error message.
        """
        return call_index_constituent_tool(
            "get_sz50_stocks",
            active_data_source.get_sz50_stocks,
            "SZ50",
            date
        )

    @app.tool()
    def get_hs300_stocks(date: Optional[str] = None) -> str:
        """
        Fetch the constituent stocks of the HS300 index on a specified date.

        Args:
            date: Optional date in 'YYYY-MM-DD' format. If None, use the latest available date.

        Returns:
            Markdown table containing HS300 constituent stocks or an error message.
        """
        return call_index_constituent_tool(
            "get_hs300_stocks",
            active_data_source.get_hs300_stocks,
            "HS300",
            date
        )

    @app.tool()
    def get_zz500_stocks(date: Optional[str] = None) -> str:
        """
        Fetch the constituent stocks of the ZZ500 index on a specified date.

        Args:
            date: Optional date in 'YYYY-MM-DD' format. If None, use the latest available date.

        Returns:
            Markdown table containing ZZ500 constituent stocks or an error message.
        """
        return call_index_constituent_tool(
            "get_zz500_stocks",
            active_data_source.get_zz500_stocks,
            "ZZ500",
            date
        )
