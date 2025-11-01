"""
Macroeconomic data tools for the MCP server.
Includes tools to fetch interest rates, money supply, and other macroeconomic indicators.
"""
import logging
from typing import Optional

from mcp.server.fastmcp import FastMCP
from src.data_source_interface import FinancialDataSource
from src.tools.base import call_macro_data_tool

logger = logging.getLogger(__name__)


def register_macroeconomic_tools(app: FastMCP, active_data_source: FinancialDataSource):
    """
    Register macroeconomic data tools to the MCP application.

    Args:
        app: FastMCP application instance.
        active_data_source: Active financial data source.
    """

    @app.tool()
    def get_deposit_rate_data(start_date: Optional[str] = None, end_date: Optional[str] = None) -> str:
        """
        Fetch benchmark deposit rate data (savings and time deposits) for a specified date range.

        Args:
            start_date: Optional start date in 'YYYY-MM-DD' format.
            end_date: Optional end date in 'YYYY-MM-DD' format.

        Returns:
            Markdown table containing deposit rate data or an error message.
        """
        return call_macro_data_tool(
            "get_deposit_rate_data",
            active_data_source.get_deposit_rate_data,
            "Deposit Rates",
            start_date, end_date
        )

    @app.tool()
    def get_loan_rate_data(start_date: Optional[str] = None, end_date: Optional[str] = None) -> str:
        """
        Fetch benchmark loan rate data for a specified date range.

        Args:
            start_date: Optional start date in 'YYYY-MM-DD' format.
            end_date: Optional end date in 'YYYY-MM-DD' format.

        Returns:
            Markdown table containing loan rate data or an error message.
        """
        return call_macro_data_tool(
            "get_loan_rate_data",
            active_data_source.get_loan_rate_data,
            "Loan Rates",
            start_date, end_date
        )

    @app.tool()
    def get_required_reserve_ratio_data(
        start_date: Optional[str] = None, end_date: Optional[str] = None, year_type: str = '0'
    ) -> str:
        """
        Fetch required reserve ratio data for a specified date range.

        Args:
            start_date: Optional start date in 'YYYY-MM-DD' format.
            end_date: Optional end date in 'YYYY-MM-DD' format.
            year_type: Optional type of year for filtering dates. '0' = announcement date (default), '1' = effective date.

        Returns:
            Markdown table containing reserve ratio data or an error message.
        """
        if year_type not in ['0', '1']:
            logger.warning(f"Invalid year_type requested: {year_type}")
            return f"Error: Invalid year_type '{year_type}'. Valid options are '0' (announcement date) or '1' (effective date)."

        return call_macro_data_tool(
            "get_required_reserve_ratio_data",
            active_data_source.get_required_reserve_ratio_data,
            "Required Reserve Ratio",
            start_date, end_date,
            yearType=year_type
        )

    @app.tool()
    def get_money_supply_data_month(start_date: Optional[str] = None, end_date: Optional[str] = None) -> str:
        """
        Fetch monthly money supply data (M0, M1, M2) for a specified date range.

        Args:
            start_date: Optional start date in 'YYYY-MM' format.
            end_date: Optional end date in 'YYYY-MM' format.

        Returns:
            Markdown table containing monthly money supply data or an error message.
        """
        return call_macro_data_tool(
            "get_money_supply_data_month",
            active_data_source.get_money_supply_data_month,
            "Monthly Money Supply",
            start_date, end_date
        )

    @app.tool()
    def get_money_supply_data_year(start_date: Optional[str] = None, end_date: Optional[str] = None) -> str:
        """
        Fetch annual money supply data (M0, M1, M2 year-end balances) for a specified date range.

        Args:
            start_date: Optional start year in 'YYYY' format.
            end_date: Optional end year in 'YYYY' format.

        Returns:
            Markdown table containing annual money supply data or an error message.
        """
        return call_macro_data_tool(
            "get_money_supply_data_year",
            active_data_source.get_money_supply_data_year,
            "Annual Money Supply",
            start_date, end_date
        )

    # @app.tool()
    # def get_shibor_data(start_date: Optional[str] = None, end_date: Optional[str] = None) -> str:
    #     """
    #     Fetch SHIBOR (Shanghai Interbank Offered Rate) data for a specified date range.
    #
    #     Args:
    #         start_date: Optional start date in 'YYYY-MM-DD' format.
    #         end_date: Optional end date in 'YYYY-MM-DD' format.
    #
    #     Returns:
    #         Markdown table containing SHIBOR data or an error message.
    #     """
    #     return call_macro_data_tool(
    #         "get_shibor_data",
    #         active_data_source.get_shibor_data,
    #         "SHIBOR",
    #         start_date, end_date
    #     )
