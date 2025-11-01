"""
Analysis tools for the MCP server.
Includes tools for generating stock analysis reports.
"""
import logging
from datetime import datetime, timedelta

from mcp.server.fastmcp import FastMCP
from src.data_source_interface import FinancialDataSource
from src.formatting.markdown_formatter import format_df_to_markdown

logger = logging.getLogger(__name__)


def register_analysis_tools(app: FastMCP, active_data_source: FinancialDataSource):
    """
    Register analysis tools to the MCP app.

    Args:
        app: FastMCP application instance
        active_data_source: Active financial data source
    """

    @app.tool()
    def get_stock_analysis(code: str, analysis_type: str = "fundamental") -> str:
        """
        Generate a data-driven stock analysis report (not investment advice).

        Args:
            code: Stock code, e.g., 'sh.600000'
            analysis_type: Type of analysis, one of 'fundamental', 'technical', or 'comprehensive'

        Returns:
            A Markdown-formatted report based on real data.
        """

        logger.info(f"Tool 'get_stock_analysis' called for {code}, type={analysis_type}")

        def safe_get_df(func, **kwargs):
            """Safely call data source functions and handle failures gracefully."""
            try:
                df = func(**kwargs)
                if df is None:
                    logger.warning(f"{func.__name__} returned None for {code}")
                    import pandas as pd
                    return pd.DataFrame()
                return df
            except Exception as e:
                logger.warning(f"Error calling {func.__name__}: {e}")
                import pandas as pd
                return pd.DataFrame()

        try:
            # Fetch basic stock info
            basic_info = safe_get_df(active_data_source.get_stock_basic_info, code=code)

            recent_year = datetime.now().year
            recent_quarter = (datetime.now().month - 1) // 3 + 1

            if analysis_type in ["fundamental", "comprehensive"]:
                profit_data = safe_get_df(active_data_source.get_profit_data, code=code, year=recent_year, quarter=recent_quarter)
                growth_data = safe_get_df(active_data_source.get_growth_data, code=code, year=recent_year, quarter=recent_quarter)
                balance_data = safe_get_df(active_data_source.get_balance_data, code=code, year=recent_year, quarter=recent_quarter)
                dupont_data = safe_get_df(active_data_source.get_dupont_data, code=code, year=recent_year, quarter=recent_quarter)
            else:
                import pandas as pd
                profit_data = growth_data = balance_data = dupont_data = pd.DataFrame()

            if analysis_type in ["technical", "comprehensive"]:
                end_date = datetime.now().strftime("%Y-%m-%d")
                start_date = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
                price_data = safe_get_df(active_data_source.get_historical_k_data, code=code, start_date=start_date, end_date=end_date)
            else:
                import pandas as pd
                price_data = pd.DataFrame()

            # Build report
            title = code
            if not basic_info.empty and "code_name" in basic_info.columns:
                title = basic_info["code_name"].values[0]

            report = f"# {title} Data Analysis Report\n\n"
            report += "## Disclaimer\nThis report is generated based on publicly available data and is for reference only. It does not constitute investment advice.\n\n"

            # Basic company info
            if not basic_info.empty:
                report += "## Company Information\n"
                report += f"- Stock Code: {code}\n"
                report += f"- Stock Name: {basic_info.get('code_name', ['Unknown'])[0]}\n"
                report += f"- Industry: {basic_info.get('industry', ['Unknown'])[0]}\n"
                report += f"- IPO Date: {basic_info.get('ipoDate', ['Unknown'])[0]}\n\n"
            else:
                report += "Company basic information not available.\n\n"

            # Fundamental analysis
            if analysis_type in ["fundamental", "comprehensive"]:
                report += f"## Fundamental Analysis (Q{recent_quarter} {recent_year})\n\n"

                if not profit_data.empty:
                    report += "### Profitability\n"
                    roe = profit_data.get("roeAvg", [None])[0]
                    npm = profit_data.get("npMargin", [None])[0]
                    if roe is not None:
                        report += f"- ROE (Return on Equity): {roe}%\n"
                    if npm is not None:
                        report += f"- Net Profit Margin: {npm}%\n"
                else:
                    report += "Profit data unavailable.\n"

                if not growth_data.empty:
                    report += "\n### Growth\n"
                    eq = growth_data.get("YOYEquity", [None])[0]
                    ni = growth_data.get("YOYNI", [None])[0]
                    if eq is not None:
                        report += f"- Year-over-Year Equity Growth: {eq}%\n"
                    if ni is not None:
                        report += f"- Year-over-Year Net Income Growth: {ni}%\n"
                else:
                    report += "Growth data unavailable.\n"

                if not balance_data.empty:
                    report += "\n### Solvency\n"
                    cr = balance_data.get("currentRatio", [None])[0]
                    dr = balance_data.get("assetLiabRatio", [None])[0]
                    if cr is not None:
                        report += f"- Current Ratio: {cr}\n"
                    if dr is not None:
                        report += f"- Debt-to-Asset Ratio: {dr}%\n"
                else:
                    report += "Balance sheet data unavailable.\n"

            # Technical analysis
            if analysis_type in ["technical", "comprehensive"]:
                report += "\n## Technical Analysis\n"
                if not price_data.empty and "close" in price_data.columns:
                    try:
                        latest_price = float(price_data["close"].iloc[-1])
                        start_price = float(price_data["close"].iloc[0])
                        change = (latest_price / start_price - 1) * 100
                        report += f"- Latest Closing Price: {latest_price:.2f}\n"
                        report += f"- 6-Month Price Change: {change:.2f}%\n"

                        if len(price_data) >= 20:
                            ma20 = price_data["close"].astype(float).tail(20).mean()
                            diff = (latest_price / ma20 - 1) * 100
                            report += f"- 20-Day Moving Average: {ma20:.2f}\n"
                            report += f"  (Current price is {'above' if diff > 0 else 'below'} the MA20 by {abs(diff):.2f}%)\n"
                    except Exception as e:
                        logger.warning(f"Error calculating technical metrics: {e}")
                        report += "Technical analysis failed.\n"
                else:
                    report += "Price data unavailable.\n"

            # Industry comparison
            try:
                if not basic_info.empty and "industry" in basic_info.columns:
                    industry = basic_info["industry"].values[0]
                    industry_df = safe_get_df(active_data_source.get_stock_industry)
                    if not industry_df.empty:
                        same = industry_df[industry_df["industry"] == industry]
                        report += f"\n## Industry Comparison ({industry})\n"
                        report += f"- Number of Stocks in the Same Industry: {len(same)}\n"
                    else:
                        report += "\nIndustry data unavailable.\n"
            except Exception as e:
                logger.warning(f"Failed to get industry comparison data: {e}")
                report += "\nIndustry comparison failed.\n"

            report += "\n## Data Interpretation Notes\n"
            report += "- The above data is for reference only; please combine it with company disclosures and industry trends.\n"
            report += "- Historical performance does not guarantee future results. Invest with caution.\n"

            logger.info(f"Successfully generated analysis report for {code}.")
            return report

        except Exception as e:
            logger.exception(f"Failed to generate analysis for {code}: {e}")
            return f"Report generation failed: {e}"
