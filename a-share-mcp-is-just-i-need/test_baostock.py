#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Complete Test Script for BaostockDataSource
"""

import sys
import os
import logging
from datetime import datetime, timedelta
import pandas as pd

# Add project path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.join(current_dir, 'a-share-mcp-is-just-i-need')
sys.path.append(project_dir)

from src.baostock_data_source import BaostockDataSource
from src.data_source_interface import NoDataFoundError, DataSourceError

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CompleteBaostockDataSourceTester:
    """Full-feature tester for BaostockDataSource"""

    def __init__(self):
        """Initialize the tester"""
        self.data_source = BaostockDataSource()
        self.test_stock_code = "sh.603871"  # Jiayou International Logistics Co., Ltd.
        self.test_year = "2023"
        self.test_quarter = 4
        self.test_start_date = "2023-01-01"
        self.test_end_date = "2023-12-31"
        self.test_count = 0
        self.success_count = 0
        self.fail_count = 0
        self.no_data_count = 0

    def test_function(self, func_name: str, test_func, *args, **kwargs):
        """Generic test runner"""
        self.test_count += 1
        print(f"\n{'=' * 60}")
        print(f"Test {self.test_count}: {func_name}")
        print(f"{'=' * 60}")

        try:
            result = test_func(*args, **kwargs)
            print(f"✅ {func_name} succeeded!")
            print(f"   Number of rows: {len(result)}")
            print(f"   Columns: {list(result.columns)}")

            if len(result) > 0:
                print(f"   Preview (first 3 rows):")
                print(result.head(3).to_string(index=False))
            else:
                print("   Data is empty")

            self.success_count += 1
            return True

        except NoDataFoundError as e:
            print(f"⚠️ {func_name} returned no data: {e}")
            self.no_data_count += 1
            return True
        except Exception as e:
            print(f"❌ {func_name} failed: {e}")
            self.fail_count += 1
            return False

    # ==================== Stock Data Tests ====================

    def test_1_get_historical_k_data(self):
        """Test 1: Historical K-line data"""
        return self.test_function(
            "get_historical_k_data",
            self.data_source.get_historical_k_data,
            code=self.test_stock_code,
            start_date="2023-12-01",
            end_date="2023-12-31",
            frequency="d",
            adjust_flag="3"
        )

    def test_2_get_stock_basic_info(self):
        """Test 2: Stock basic info"""
        return self.test_function(
            "get_stock_basic_info",
            self.data_source.get_stock_basic_info,
            code=self.test_stock_code
        )

    def test_3_get_dividend_data(self):
        """Test 3: Dividend data"""
        return self.test_function(
            "get_dividend_data",
            self.data_source.get_dividend_data,
            code=self.test_stock_code,
            year=self.test_year,
            year_type="report"
        )

    def test_4_get_adjust_factor_data(self):
        """Test 4: Adjust factor data"""
        return self.test_function(
            "get_adjust_factor_data",
            self.data_source.get_adjust_factor_data,
            code=self.test_stock_code,
            start_date=self.test_start_date,
            end_date=self.test_end_date
        )

    # ==================== Financial Data Tests ====================

    def test_5_get_profit_data(self):
        """Test 5: Profitability data"""
        return self.test_function(
            "get_profit_data",
            self.data_source.get_profit_data,
            code=self.test_stock_code,
            year=self.test_year,
            quarter=self.test_quarter
        )

    def test_6_get_operation_data(self):
        """Test 6: Operational ability data"""
        return self.test_function(
            "get_operation_data",
            self.data_source.get_operation_data,
            code=self.test_stock_code,
            year=self.test_year,
            quarter=self.test_quarter
        )

    def test_7_get_growth_data(self):
        """Test 7: Growth ability data"""
        return self.test_function(
            "get_growth_data",
            self.data_source.get_growth_data,
            code=self.test_stock_code,
            year=self.test_year,
            quarter=self.test_quarter
        )

    def test_8_get_balance_data(self):
        """Test 8: Solvency data"""
        return self.test_function(
            "get_balance_data",
            self.data_source.get_balance_data,
            code=self.test_stock_code,
            year=self.test_year,
            quarter=self.test_quarter
        )

    def test_9_get_cash_flow_data(self):
        """Test 9: Cash flow data"""
        return self.test_function(
            "get_cash_flow_data",
            self.data_source.get_cash_flow_data,
            code=self.test_stock_code,
            year=self.test_year,
            quarter=self.test_quarter
        )

    def test_10_get_dupont_data(self):
        """Test 10: DuPont analysis"""
        return self.test_function(
            "get_dupont_data",
            self.data_source.get_dupont_data,
            code=self.test_stock_code,
            year=self.test_year,
            quarter=self.test_quarter
        )

    # ==================== Performance Reports ====================

    def test_11_get_performance_express_report(self):
        """Test 11: Performance express report"""
        return self.test_function(
            "query_performance_express_report",
            self.data_source.get_performance_express_report,
            code="sh.600000",
            start_date="2015-01-01",
            end_date="2015-12-31"
        )

    def test_12_get_forecast_report(self):
        """Test 12: Performance forecast report"""
        return self.test_function(
            "get_forecast_report",
            self.data_source.get_forecast_report,
            code=self.test_stock_code,
            start_date=self.test_start_date,
            end_date=self.test_end_date
        )

    # ==================== Market Data Tests ====================

    def test_13_get_stock_industry(self):
        """Test 13: Stock industry classification"""
        return self.test_function(
            "get_stock_industry",
            self.data_source.get_stock_industry,
            code=self.test_stock_code
        )

    def test_14_get_sz50_stocks(self):
        """Test 14: SSE 50 constituent stocks"""
        return self.test_function(
            "get_sz50_stocks",
            self.data_source.get_sz50_stocks
        )

    def test_15_get_hs300_stocks(self):
        """Test 15: CSI 300 constituent stocks"""
        return self.test_function(
            "get_hs300_stocks",
            self.data_source.get_hs300_stocks
        )

    def test_16_get_zz500_stocks(self):
        """Test 16: CSI 500 constituent stocks"""
        return self.test_function(
            "get_zz500_stocks",
            self.data_source.get_zz500_stocks
        )

    def test_17_get_trade_dates(self):
        """Test 17: Trading calendar"""
        return self.test_function(
            "get_trade_dates",
            self.data_source.get_trade_dates,
            start_date="2023-01-01",
            end_date="2023-01-31"
        )

    def test_18_get_all_stock(self):
        """Test 18: Full market stock list"""
        return self.test_function(
            "query_all_stock",
            self.data_source.get_all_stock,
            "2017-06-30"
        )

    # ==================== Macroeconomic Data Tests ====================

    def test_19_get_deposit_rate_data(self):
        """Test 19: Deposit rate data"""
        return self.test_function(
            "query_deposit_rate_data",
            self.data_source.get_deposit_rate_data,
            start_date="2015-01-01",
            end_date="2015-12-31"
        )

    def test_20_get_loan_rate_data(self):
        """Test 20: Loan rate data"""
        return self.test_function(
            "query_loan_rate_data",
            self.data_source.get_loan_rate_data,
            start_date="2015-01-01",
            end_date="2015-12-31"
        )

    def test_21_get_required_reserve_ratio_data(self):
        """Test 21: Required reserve ratio data"""
        return self.test_function(
            "query_required_reserve_ratio_data",
            self.data_source.get_required_reserve_ratio_data,
            start_date="2015-01-01",
            end_date="2015-12-31"
        )

    def test_22_get_money_supply_data_month(self):
        """Test 22: Monthly money supply data"""
        return self.test_function(
            "get_money_supply_data_month",
            self.data_source.get_money_supply_data_month,
            start_date="2023-01",
            end_date="2023-12"
        )

    def test_23_get_money_supply_data_year(self):
        """Test 23: Yearly money supply data"""
        return self.test_function(
            "get_money_supply_data_year",
            self.data_source.get_money_supply_data_year,
            start_date="2023",
            end_date="2023"
        )

    # ==================== News Crawler Test ====================

    def test_25_crawl_news(self):
        """Test 25: News crawling"""
        print(f"\n{'=' * 60}")
        print(f"Test {self.test_count + 1}: crawl_news")
        print(f"{'=' * 60}")

        test_queries = [
            "Jiayou International",
        ]

        success_count = 0
        total_count = len(test_queries)

        for query in test_queries:
            print(f"Query: '{query}'")
            print("-" * 50)

            try:
                result = self.data_source.crawl_news(query, 3)
                print("✅ News crawling succeeded!")
                print(f"   Query: {query}")
                print(f"   Result: {result}")
                success_count += 1

            except Exception as e:
                print(f"❌ News crawling failed: {e}")

            print("\n" + "=" * 60 + "\n")

        self.test_count += 1
        if success_count == total_count:
            self.success_count += 1
            print(f"✅ crawl_news test succeeded! ({success_count}/{total_count})")
        else:
            self.fail_count += 1
            print(f"❌ crawl_news test failed! ({success_count}/{total_count})")

        return success_count == total_count

    # ==================== Run All Tests ====================

    def run_all_tests(self):
        """Run all tests"""
        print("🚀 Starting full BaostockDataSource test")
        print(f"📊 Test Stock: {self.test_stock_code} (Jiayou International Logistics Co., Ltd.)")
        print(f"📅 Test date range: {self.test_start_date} to {self.test_end_date}")
        print(f"📈 Test year: {self.test_year} Q{self.test_quarter}")

        # Run all tests
        tests = [
            # Stock data
            self.test_1_get_historical_k_data,
            self.test_2_get_stock_basic_info,
            self.test_3_get_dividend_data,
            self.test_4_get_adjust_factor_data,

            # Financial data
            self.test_5_get_profit_data,
            self.test_6_get_operation_data,
            self.test_7_get_growth_data,
            self.test_8_get_balance_data,
            self.test_9_get_cash_flow_data,
            self.test_10_get_dupont_data,

            # Performance reports
            self.test_11_get_performance_express_report,
            self.test_12_get_forecast_report,

            # Market data
            self.test_13_get_stock_industry,
            self.test_14_get_sz50_stocks,
            self.test_15_get_hs300_stocks,
            self.test_16_get_zz500_stocks,
            self.test_17_get_trade_dates,
            self.test_18_get_all_stock,

            # Macroeconomic data
            self.test_19_get_deposit_rate_data,
            self.test_20_get_loan_rate_data,
            self.test_21_get_required_reserve_ratio_data,
            self.test_22_get_money_supply_data_month,
            self.test_23_get_money_supply_data_year,

            # News crawling
            self.test_25_crawl_news,
        ]

        for test in tests:
            test()

        # Output summary
        print("\n" + "=" * 60)
        print("📊 Full test summary")
        print("=" * 60)
        print(f"Total tests: {self.test_count}")
        print(f"Success: {self.success_count}")
        print(f"No data: {self.no_data_count}")
        print(f"Failed: {self.fail_count}")
        print(f"Success rate: {(self.success_count + self.no_data_count) / self.test_count * 100:.1f}%")

        # Detailed breakdown
        print(f"\n📈 Breakdown:")
        print(f"   ✅ Successful: {self.success_count}")
        print(f"   ⚠️ No data: {self.no_data_count}")
        print(f"   ❌ Failed: {self.fail_count}")

        if self.fail_count == 0:
            print("\n🎉 All tests passed!")
        else:
            print(f"\n⚠️ {self.fail_count} tests failed. Please check the corresponding functions.")

        print("=" * 60)


def main():
    """Main function"""
    try:
        tester = CompleteBaostockDataSourceTester()
        tester.run_all_tests()
    except KeyboardInterrupt:
        print("\n⚠️ Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        logger.exception("Error during testing")


if __name__ == "__main__":
    main()
