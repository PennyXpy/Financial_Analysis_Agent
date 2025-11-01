"""
Date utilities for MCP server.
Includes tools for obtaining the current date and the latest trading date.
"""
import logging
from datetime import datetime, timedelta
import calendar

from mcp.server.fastmcp import FastMCP
from src.data_source_interface import FinancialDataSource

logger = logging.getLogger(__name__)


def register_date_utils_tools(app: FastMCP, active_data_source: FinancialDataSource):
    """
    Register date utility tools to the MCP application.

    Args:
        app: FastMCP application instance.
        active_data_source: Active financial data source.
    """

    # @app.tool()
    # def get_current_date() -> str:
    #     """
    #     Get the current date, which can be used to query the latest data.
    #
    #     Returns:
    #         The current date in 'YYYY-MM-DD' format.
    #     """
    #     logger.info("Tool 'get_current_date' called")
    #     current_date = datetime.now().strftime("%Y-%m-%d")
    #     logger.info(f"Returning current date: {current_date}")
    #     return current_date

    @app.tool()
    def get_latest_trading_date() -> str:
        """
        Get the most recent trading date. If today is a trading day, return today's date;
        otherwise, return the latest trading date.

        Returns:
            The latest trading date in 'YYYY-MM-DD' format.
        """
        logger.info("Tool 'get_latest_trading_date' called")
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            # Get the trading calendar for roughly this month
            start_date = (datetime.now().replace(day=1)).strftime("%Y-%m-%d")
            end_date = (datetime.now().replace(day=28)).strftime("%Y-%m-%d")

            df = active_data_source.get_trade_dates(
                start_date=start_date, end_date=end_date)

            # Filter valid trading days
            valid_trading_days = df[df['is_trading_day']
                                    == '1']['calendar_date'].tolist()

            # Find the largest date less than or equal to today
            latest_trading_date = None
            for date in valid_trading_days:
                if date <= today and (latest_trading_date is None or date > latest_trading_date):
                    latest_trading_date = date

            if latest_trading_date:
                logger.info(
                    f"Latest trading date found: {latest_trading_date}")
                return latest_trading_date
            else:
                logger.warning(
                    "No trading dates found before today, returning today's date")
                return today

        except Exception as e:
            logger.exception(f"Error determining latest trading date: {e}")
            return datetime.now().strftime("%Y-%m-%d")

    @app.tool()
    def get_market_analysis_timeframe(period: str = "recent") -> str:
        """
        Get a suitable timeframe for market analysis, based on the actual current date
        rather than training data. This tool should be called before performing market
        or index analysis to ensure the use of the most up-to-date data.

        Args:
            period: Time range type. Options:
                    "recent" (default): Last 1–2 months
                    "quarter": Last quarter
                    "half_year": Last 6 months
                    "year": Last year

        Returns:
            A descriptive string containing the analysis timeframe, formatted like
            "YYYY-MM to YYYY-MM (ISO date range: YYYY-MM-DD to YYYY-MM-DD)".
        """
        logger.info(
            f"Tool 'get_market_analysis_timeframe' called with period={period}")

        now = datetime.now()
        end_date = now

        # Determine start date based on the requested period
        if period == "recent":
            # Last 1–2 months
            if now.day < 15:
                # If it's early in the month, look at the past two months
                if now.month == 1:
                    start_date = datetime(now.year - 1, 11, 1)
                    middle_date = datetime(now.year - 1, 12, 1)
                elif now.month == 2:
                    start_date = datetime(now.year, 1, 1)
                    middle_date = start_date
                else:
                    start_date = datetime(now.year, now.month - 2, 1)
                    middle_date = datetime(now.year, now.month - 1, 1)
            else:
                # If it's mid- or late-month, look at the last month
                if now.month == 1:
                    start_date = datetime(now.year - 1, 12, 1)
                    middle_date = start_date
                else:
                    start_date = datetime(now.year, now.month - 1, 1)
                    middle_date = start_date

        elif period == "quarter":
            # Last quarter (~3 months)
            if now.month <= 3:
                start_date = datetime(now.year - 1, now.month + 9, 1)
            else:
                start_date = datetime(now.year, now.month - 3, 1)
            middle_date = start_date

        elif period == "half_year":
            # Last half year
            if now.month <= 6:
                start_date = datetime(now.year - 1, now.month + 6, 1)
            else:
                start_date = datetime(now.year, now.month - 6, 1)
            middle_date = datetime(start_date.year, start_date.month + 3, 1) if start_date.month <= 9 else \
                datetime(start_date.year + 1, start_date.month - 9, 1)

        elif period == "year":
            # Last year
            start_date = datetime(now.year - 1, now.month, 1)
            middle_date = datetime(start_date.year, start_date.month + 6, 1) if start_date.month <= 6 else \
                datetime(start_date.year + 1, start_date.month - 6, 1)
        else:
            # Default: last month
            if now.month == 1:
                start_date = datetime(now.year - 1, 12, 1)
            else:
                start_date = datetime(now.year, now.month - 1, 1)
            middle_date = start_date

        # Format the dates for display
        def get_month_end_day(year, month):
            return calendar.monthrange(year, month)[1]

        end_day = min(get_month_end_day(
            end_date.year, end_date.month), end_date.day)
        end_display_date = f"{end_date.year}-{end_date.month:02d}"
        end_iso_date = f"{end_date.year}-{end_date.month:02d}-{end_day:02d}"

        start_display_date = f"{start_date.year}-{start_date.month:02d}"
        start_iso_date = f"{start_date.year}-{start_date.month:02d}-01"

        # Create readable range
        if start_date.year != end_date.year:
            date_range = f"{start_date.year}-{start_date.month} to {end_date.year}-{end_date.month}"
        elif middle_date.month != start_date.month and middle_date.month != end_date.month:
            date_range = f"{start_date.year}-{start_date.month} to {middle_date.month} to {end_date.month}"
        elif start_date.month != end_date.month:
            date_range = f"{start_date.year}-{start_date.month} to {end_date.month}"
        else:
            date_range = f"{start_date.year}-{start_date.month}"

        result = f"{date_range} (ISO date range: {start_iso_date} to {end_iso_date})"
        logger.info(f"Generated market analysis timeframe: {result}")
        return result
