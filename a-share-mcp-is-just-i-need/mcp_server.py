# Main MCP server file
import logging
from datetime import datetime

from mcp.server.fastmcp import FastMCP

# Import the interface and the concrete implementation
from src.data_source_interface import FinancialDataSource
from src.baostock_data_source import BaostockDataSource
from src.utils import setup_logging

# Import registration functions for various tools/modules
from src.tools.stock_market import register_stock_market_tools
from src.tools.financial_reports import register_financial_report_tools
from src.tools.indices import register_index_tools
from src.tools.market_overview import register_market_overview_tools
from src.tools.macroeconomic import register_macroeconomic_tools
from src.tools.date_utils import register_date_utils_tools
from src.tools.analysis import register_analysis_tools
from src.tools.news_crawler import register_news_crawler_tools

# --- Logging Setup ---
# Call the setup function from utils
# You can control the default level here (e.g., logging.DEBUG for more verbose logs)
setup_logging(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Dependency Injection ---
# Instantiate the data source - easy to swap later if needed
active_data_source: FinancialDataSource = BaostockDataSource()

# --- Get current date for system prompt ---
current_date = datetime.now().strftime("%Y-%m-%d")

# --- FastMCP App Initialization ---
app = FastMCP(
#     server_name="a_share_data_provider",
#     description=f"""Today is {current_date}. This service provides tools for analyzing the Chinese A-Share market.
# The service delivers objective data analysis. Users are responsible for making their own investment decisions.
# Data analysis is based on publicly available market information and does not constitute investment advice; for reference only.

# ⚠️ Important Notes:
# 1. The latest trading day may not be today; use get_latest_trading_date() to retrieve it.
# 2. Always use get_latest_trading_date() to get the actual most recent trading day; do not rely on dates in training data.
# 3. When analyzing "recent" market conditions, always call get_market_analysis_timeframe() to determine the actual analysis time frame.
# 4. Any date-related analysis must be based on actual data returned by tools; do not use outdated or assumed dates.
# 5. New news crawler functionality allows searching for company- or industry-related news to support investment decisions.
# """,
    # Specify dependencies for installation if needed (e.g., when using `mcp install`)
    # dependencies=["baostock", "pandas"]
)

# --- Register tools for each module ---
register_stock_market_tools(app, active_data_source)
register_financial_report_tools(app, active_data_source)
register_index_tools(app, active_data_source)
register_market_overview_tools(app, active_data_source)
register_macroeconomic_tools(app, active_data_source)
register_date_utils_tools(app, active_data_source)
register_analysis_tools(app, active_data_source)
register_news_crawler_tools(app, active_data_source)

# --- Main Execution Block ---
if __name__ == "__main__":
    logger.info(f"Starting A-Share MCP Server via stdio... Today is {current_date}")
    # Run the server using stdio transport, suitable for MCP Hosts like Claude Desktop
    app.run(transport='stdio')
