"""
News Crawler Tool Module
Provides news search and scraping functionality.
"""

import logging
from typing import List, Dict
from mcp.server.fastmcp import FastMCP
from ..data_source_interface import FinancialDataSource

logger = logging.getLogger(__name__)


def register_news_crawler_tools(app: FastMCP, data_source: FinancialDataSource):
    """
    Register news crawler tools with the MCP application.

    Args:
        app: FastMCP application instance.
        data_source: Data source instance.
    """

    @app.tool()
    def crawl_news(query: str, top_k: int = 10) -> str:
        """
        Crawl related news articles.

        Uses Baidu search to fetch news articles relevant to the query term and returns
        a formatted result.

        Args:
            query: Search query string, e.g., "Jiayou International" or "AI investment".
            top_k: Number of news articles to return. Default is 10.

        Returns:
            Formatted string of news results, including title, summary, and link.

        Example:
            >>> crawl_news("Jiayou International", 5)
            "Found the following news articles:

            1. Jiayou International releases Q1 2024 financial report
               Source: Baidu Search
               Summary: Jiayou International today released its Q1 2024 financial report, revenue up 15% YoY...
               Link: https://example.com/news/123
            "
        """
        try:
            logger.info(f"Starting news crawl for query: {query}, top_k: {top_k}")
            result = data_source.crawl_news(query, top_k)
            logger.info(f"News crawl completed, result length: {len(result)}")
            return result
        except Exception as e:
            logger.error(f"Error occurred while crawling news: {e}")
            return f"Error occurred while crawling news: {str(e)}"
