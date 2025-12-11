# US Stock Support Implementation

## Overview
This document describes the implementation of US stock support using Yahoo Finance data source.

## Changes Made

### 1. New Files Created

#### `yahoo_finance_data_source.py`
- Implements `FinancialDataSource` interface
- Uses `yfinance` library to fetch US stock data
- Supports historical K-line data, basic info, and dividend data
- Converts data format to match Baostock format for consistency

#### `multi_data_source.py`
- Multi-data source adapter that automatically selects the appropriate data source
- Routes A-share stocks (sh.xxxxxx, sz.xxxxxx) to BaostockDataSource
- Routes US stocks (AAPL, TSLA, etc.) to YahooFinanceDataSource

### 2. Modified Files

#### `mcp_server.py`
- Changed from using `BaostockDataSource()` to `MultiDataSource()`
- Now supports both A-share and US stocks automatically

#### `main.py` (Financial-MCP-Agent)
- Updated stock code recognition logic
- Now recognizes US stock codes (1-5 uppercase letters)
- Adds market type information to initial data

#### `data_source_interface.py`
- Updated `get_stock_basic_info` signature to include optional `fields` parameter

#### `requirements.txt`
- Added `yfinance==0.2.40` dependency

## Usage

### A-Share Stocks (Existing Functionality)
```python
# A-share stocks work as before
stock_code = "sh.600519"  # 茅台
stock_code = "sz.000001"  # 平安银行
```

### US Stocks (New Functionality)
```python
# US stocks now supported
stock_code = "AAPL"  # Apple
stock_code = "TSLA"  # Tesla
stock_code = "MSFT"  # Microsoft
```

### Query Examples
```
# Chinese
"分析苹果 (AAPL)"
"帮我看看特斯拉这只股票怎么样"

# English
"Analyze Apple (AAPL)"
"Please analyze Tesla stock"
"What about Microsoft (MSFT)?"
```

## Data Source Selection Logic

The `MultiDataSource` automatically selects the data source based on stock code format:

1. **A-Share Format** (`sh.xxxxxx` or `sz.xxxxxx`)
   - Uses `BaostockDataSource`
   - Supports all A-share specific features (financial reports, indices, etc.)

2. **US Stock Format** (1-5 uppercase letters, e.g., `AAPL`, `TSLA`)
   - Uses `YahooFinanceDataSource`
   - Supports historical data, basic info, and dividend data
   - Note: Financial reports (quarterly data) are not fully available from Yahoo Finance

3. **Unknown Format**
   - Defaults to Yahoo Finance (may support international stocks)

## Limitations

### Yahoo Finance Data Source
- Financial reports (profit, balance sheet, cash flow) are not fully implemented
- Some A-share specific features (trading dates, money supply, etc.) are not available
- Dividend data is available but may have different format

### Multi-DataSource
- A-share specific tools (indices, macroeconomic data) will only work with A-share stocks
- US stock analysis may have limited financial report data compared to A-shares

## Installation

Make sure to install the new dependency:

```bash
pip install yfinance==0.2.40
```

Or install all dependencies:

```bash
pip install -r requirements.txt
```

## Testing

You can test US stock support by:

1. Running the MCP server:
```bash
cd a-share-mcp-is-just-i-need
python mcp_server.py
```

2. Using the Financial Agent:
```bash
cd Financial-MCP-Agent
python -m src.main --command "Analyze Apple (AAPL)"
```

## Future Enhancements

- Add support for more international markets (Hong Kong stocks, etc.)
- Implement financial report fetching for US stocks using alternative APIs
- Add more comprehensive error handling for unsupported stock codes
- Add market detection based on company name matching

