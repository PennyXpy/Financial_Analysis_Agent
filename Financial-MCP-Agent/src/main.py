"""
金融分析智能体系统主程序 (Financial Analysis AI Agent System Main Program)

本文件是金融分析智能体系统的核心入口点，实现了以下主要功能：

1. 多智能体工作流管理：使用LangGraph构建并行执行的智能体工作流
2. 命令行界面：提供用户友好的交互式命令行界面
3. 自然语言处理：自动识别和提取股票代码、公司名称
4. 日志系统：完整的执行日志记录和错误处理
5. 报告生成：生成综合性的金融分析报告

工作流程：
start_node → [fundamental_analyst, technical_analyst, value_analyst] → summarizer → END
"""

# ============================================================================
# 导入必要的模块和依赖
# ============================================================================

# 在导入其他模块之前设置环境变量，抑制无用输出
import os
import sys

# 设置环境变量来抑制transformers和其他库的冗余输出
os.environ["TRANSFORMERS_VERBOSITY"] = "error"  # 只显示错误信息
os.environ["TOKENIZERS_PARALLELISM"] = "false"  # 禁用tokenizer并行化警告
os.environ["CUDA_LAUNCH_BLOCKING"] = "1"  # 减少CUDA相关输出
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "max_split_size_mb:128"  # 减少内存分配信息

# 设置日志级别，抑制第三方库的INFO级别输出
import logging
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("accelerate").setLevel(logging.ERROR)
logging.getLogger("torch").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("requests").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)

# 日志和状态管理相关导入
from src.utils.logging_config import setup_logger, SUCCESS_ICON, ERROR_ICON, WAIT_ICON
from src.utils.state_definition import AgentState
from src.utils.execution_logger import initialize_execution_logger, finalize_execution_logger, get_execution_logger

# 智能体模块导入 - 五个核心分析智能体
from src.agents.summary_agent import summary_agent      # 总结智能体：整合所有分析结果
from src.agents.value_agent import value_agent          # 估值智能体：分析股票估值水平
from src.agents.technical_agent import technical_agent  # 技术分析智能体：分析价格趋势和技术指标
from src.agents.fundamental_agent import fundamental_agent  # 基本面智能体：分析财务状况和盈利能力
from src.agents.news_agent import news_agent            # 新闻分析智能体：分析新闻情感和风险

# LangGraph工作流框架导入
from langgraph.graph import StateGraph, END

# 环境变量和系统相关导入
from dotenv import load_dotenv
import argparse
import asyncio
import re
from datetime import datetime

# ============================================================================
# 初始化和配置
# ============================================================================

# 设置日志记录器
logger = setup_logger(__name__)

# 添加项目根目录到Python路径，确保模块导入正常工作
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

# 加载环境变量（从.env文件）
load_dotenv(override=True)

# 调试：打印关键环境变量以验证配置
logger.info(f"Environment Variables Loaded:")
logger.info(
    f"  OPENAI_COMPATIBLE_MODEL: {os.getenv('OPENAI_COMPATIBLE_MODEL', 'Not Set')}")
logger.info(
    f"  OPENAI_COMPATIBLE_BASE_URL: {os.getenv('OPENAI_COMPATIBLE_BASE_URL', 'Not Set')}")
logger.info(
    f"  OPENAI_COMPATIBLE_API_KEY: {'*' * 20 if os.getenv('OPENAI_COMPATIBLE_API_KEY') else 'Not Set'}")

# 重新设置日志记录器（确保正确配置）
logger = setup_logger(__name__)


async def main():
    """
    主函数：金融分析智能体系统的核心执行逻辑
    
    功能包括：
    1. 初始化执行日志系统
    2. 构建LangGraph工作流
    3. 处理命令行参数和用户输入
    4. 提取股票信息（代码、公司名称）
    5. 执行多智能体分析工作流
    6. 生成和保存分析报告
    7. 错误处理和日志记录
    """
    
    # 初始化执行日志系统
    execution_logger = initialize_execution_logger()
    logger.info(
        f"{SUCCESS_ICON} Execution logger initialized, log directory: {execution_logger.execution_dir}")

    # ============================================================================
    # 🔧 全局初始化 MCP Client（生命周期管理）
    # ============================================================================
    logger.info(f"{WAIT_ICON} Pre-initializing MCP Client (global singleton)...")
    from src.tools.mcp_client import get_mcp_tools
    
    try:
        # 在主流程开始前初始化 MCP tools
        # 这确保只有一个 MCP server 进程，由主流程控制生命周期
        global_mcp_tools = await get_mcp_tools()
        if not global_mcp_tools:
            logger.error(f"{ERROR_ICON} Failed to initialize MCP tools. System cannot proceed.")
            print(f"\n{ERROR_ICON} Failed to initialize MCP tools. Please check MCP server configuration.")
            return
        logger.info(f"{SUCCESS_ICON} MCP Client initialized successfully with {len(global_mcp_tools)} tools.")
    except Exception as e:
        logger.error(f"{ERROR_ICON} Failed to initialize MCP Client: {e}", exc_info=True)
        print(f"\n{ERROR_ICON} Failed to initialize MCP Client: {e}")
        return

    try:
        # ============================================================================
        # 1. 定义LangGraph工作流 
        # ============================================================================
        
        # 创建工作流图，使用AgentState作为状态类型
        workflow = StateGraph(AgentState)

        # 添加起始节点 - 作为并行分支的清晰起点
        workflow.add_node("start_node", lambda state: state)

        # 添加五个核心智能体节点
        workflow.add_node("fundamental_analyst", fundamental_agent)  # 基本面分析智能体
        workflow.add_node("technical_analyst", technical_agent)      # 技术分析智能体
        workflow.add_node("value_analyst", value_agent)             # 估值分析智能体
        workflow.add_node("news_analyst", news_agent)               # 新闻分析智能体
        workflow.add_node("summarizer", summary_agent)              # 总结智能体

        # 设置工作流入口点
        workflow.set_entry_point("start_node")

        # ⚠️ 改为串行执行 - 避免并发导致的 MCP server 冲突
        # 执行顺序：start → fundamental → technical → value → news → summarizer
        workflow.add_edge("start_node", "fundamental_analyst")
        workflow.add_edge("fundamental_analyst", "technical_analyst")
        workflow.add_edge("technical_analyst", "value_analyst")
        workflow.add_edge("value_analyst", "news_analyst")
        workflow.add_edge("news_analyst", "summarizer")

        # 添加结束边 - 总结智能体完成后结束工作流
        workflow.add_edge("summarizer", END)

        # 编译工作流
        app = workflow.compile()

        # ============================================================================
        # 2. 实现命令行界面 
        # ============================================================================
        
        # 创建命令行参数解析器
        parser = argparse.ArgumentParser(description="Financial Agent CLI")
        parser.add_argument(
            "--command",
            type=str,
            required=False,  # 改为非必需，支持交互式输入
            help="The user query for financial analysis (e.g., '分析嘉友国际')"
        )
        args = parser.parse_args()

        # 处理用户查询输入
        if args.command:
            # 如果通过命令行参数提供查询
            user_query = args.command
        else:
            # 显示ASCII艺术开屏图像和交互式界面
            print("\n")
            print(
                "╔══════════════════════════════════════════════════════════════════════════════╗")
            print(
                "║                                                                              ║")
            print(
                "║      ███████╗██╗███╗   ██╗ █████╗ ███╗   ██╗ ██████╗██╗ █████╗ ██╗          ║")
            print(
                "║      ██╔════╝██║████╗  ██║██╔══██╗████╗  ██║██╔════╝██║██╔══██╗██║          ║")
            print(
                "║      █████╗  ██║██╔██╗ ██║███████║██╔██╗ ██║██║     ██║███████║██║          ║")
            print(
                "║      ██╔══╝  ██║██║╚██╗██║██╔══██║██║╚██╗██║██║     ██║██╔══██║██║          ║")
            print(
                "║      ██║     ██║██║ ╚████║██║  ██║██║ ╚████║╚██████╗██║██║  ██║███████╗      ║")
            print(
                "║      ╚═╝     ╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝╚═╝╚═╝  ╚═╝╚══════╝      ║")
            print(
                "║                                                                              ║")
            print(
                "║                █████╗  ██████╗ ███████╗███╗   ██╗████████╗                  ║")
            print(
                "║               ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝                  ║")
            print(
                "║               ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║                     ║")
            print(
                "║               ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║                     ║")
            print(
                "║               ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║                     ║")
            print(
                "║               ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝                     ║")
            print(
                "║                                                                              ║")
            print("║                          🏦 Financial Analysis Agent System                  ║")
            print(
                "║                     Financial Analysis AI Agent System                      ║")
            print(
                "║                                                                              ║")
            print(
                "║    ┌─────────────────────────────────────────────────────────────────┐     ║")
            print("║    │  📊 Fundamental  │  📈 Technical  │  💰 Valuation  │  📰 News  │  🤖 Summary  │    ║")
            print(
                "║    └─────────────────────────────────────────────────────────────────┘     ║")
            print(
                "║                                                                              ║")
            print(
                "╚══════════════════════════════════════════════════════════════════════════════╝")
            print("\n🔹 This system can analyze A-share companies, including:")
            print("  • Fundamental Analysis - Financial status, profitability, and industry position")
            print("  • Technical Analysis - Price trends, trading volume, and technical indicators")
            print("  • Valuation Analysis - P/E ratio, P/B ratio, and other valuation metrics")
            print("  • News Analysis - News sentiment analysis and risk assessment")
            print("\n🔹 Supports multiple natural language query formats:")
            print("  • 分析嘉友国际")
            print("  • 帮我看看比亚迪这只股票怎么样")
            print("  • Analyze Apple (AAPL)")
            print("  • Please analyze Tesla stock")
            print("  • 603871 这个股票值得买吗？")
            print("\n🔹 You can use any natural language to describe your analysis needs")
            print("🔹 The system will automatically identify stock names and codes, and perform comprehensive analysis")
            print("\n💡 Tip: Using stock codes (e.g., 000001, 600036) will provide more accurate results")
            print("\n" + "─" * 78 + "\n")

            # 获取用户输入
            user_query = input("💬 Please enter your analysis request: ")

            # 确保输入不为空
            while not user_query.strip():
                print(f"{ERROR_ICON} Input cannot be empty, please try again!")
                user_query = input("Please enter your analysis request: ")

        # 记录用户查询到执行日志
        execution_logger.log_agent_start("main", {"user_query": user_query})

        # ============================================================================
        # 3. 自然语言处理和股票信息提取
        # ============================================================================
        
        # 从查询中提取股票代码和公司名称
        stock_code = None
        company_name = None

        # 定义更精确的提取模式
        # Note: re module is imported at the top of the file
        def extract_stock_info(query):
            """精确提取股票代码和公司名称"""
            import re  # Import re inside the function to ensure it's available
            stock_code = None
            company_name = None
            
            # 模式1: 包含"请帮我分析一下"的复杂查询，如"请帮我分析一下嘉友国际(603871)这只股票的投资价值如何"
            pattern1 = r'请帮我分析一下\s*([^（(]+?)\s*[（(](\d{5,6})[)）]'
            match1 = re.search(pattern1, query)
            if match1:
                company_name = match1.group(1).strip()
                stock_code = match1.group(2)
                return company_name, stock_code
            
            # 模式2: 包含"分析一下"的复杂查询，如"分析一下嘉友国际(603871)的财务状况"
            pattern2 = r'分析一下\s*([^（(]+?)\s*[（(](\d{5,6})[)）]'
            match2 = re.search(pattern2, query)
            if match2:
                company_name = match2.group(1).strip()
                stock_code = match2.group(2)
                return company_name, stock_code
            
            # 模式3: 股票代码在括号内，如"分析嘉友国际(603871)"
            pattern3 = r'分析\s*([^（(]+?)\s*[（(](\d{5,6})[)）]'
            match3 = re.search(pattern3, query)
            if match3:
                company_name = match3.group(1).strip()
                stock_code = match3.group(2)
                return company_name, stock_code
            
            # 模式4: 股票代码在括号内，如"分析(603871)嘉友国际"
            pattern4 = r'分析\s*[（(](\d{5,6})[)）]\s*([^）)]+)'
            match4 = re.search(pattern4, query)
            if match4:
                stock_code = match4.group(1)
                company_name = match4.group(2).strip()
                return company_name, stock_code
            
            # 模式5: 包含"帮我看看"的查询，如"帮我看看(000001)平安银行这只股票"
            pattern5 = r'帮我看看\s*[（(](\d{5,6})[)）]\s*([^）)]+?)(?:\s*这只|\s*这个)?\s*股票'
            match5 = re.search(pattern5, query)
            if match5:
                stock_code = match5.group(1)
                company_name = match5.group(2).strip()
                return company_name, stock_code
            
            # 模式6: 包含"我想了解一下"的查询，如"我想了解一下比亚迪(002594)的投资价值"
            pattern6 = r'我想了解一下\s*([^（(]+?)\s*[（(](\d{5,6})[)）]'
            match6 = re.search(pattern6, query)
            if match6:
                company_name = match6.group(1).strip()
                stock_code = match6.group(2)
                return company_name, stock_code
            
            # 模式7: 包含"帮我看看"的复杂查询，如"帮我看看茅台(600519)这只股票值得投资吗"
            pattern7 = r'帮我看看\s*([^（(]+?)\s*[（(](\d{5,6})[)）]'
            match7 = re.search(pattern7, query)
            if match7:
                company_name = match7.group(1).strip()
                stock_code = match7.group(2)
                return company_name, stock_code
            
            # 模式8: 直接公司名+括号格式，如"平安银行(000001)值得买吗"
            pattern8 = r'^([^（(]+?)\s*[（(](\d{5,6})[)）]'
            match8 = re.search(pattern8, query)
            if match8:
                company_name = match8.group(1).strip()
                stock_code = match8.group(2)
                return company_name, stock_code
            
            # 模式9: 包含"分析一下"的查询，如"分析一下宁德时代的财务状况"
            pattern9 = r'分析一下\s*([^0-9（）()\s]+?)(?:\s*的|\s|$)'
            match9 = re.search(pattern9, query)
            if match9:
                company_name = match9.group(1).strip()
            
            # 模式10: 包含"分析"关键词，如"分析嘉友国际"
            pattern10 = r'分析\s*([^0-9（）()\s]+)'
            match10 = re.search(pattern10, query)
            if match10 and not company_name:
                company_name = match10.group(1).strip()
            
            # 模式11: 包含"股票"关键词的查询，如"嘉友国际这只股票怎么样"
            pattern11 = r'([^0-9（）()\s]+)\s*(?:这只|这个|的)?\s*股票'
            match11 = re.search(pattern11, query)
            if match11 and not company_name:
                company_name = match11.group(1).strip()
            
            # 模式12: 包含"投资价值"的查询，如"了解一下腾讯的投资价值"
            pattern12 = r'了解一下\s*([^0-9（）()\s]+?)(?:\s*的|\s|$)'
            match12 = re.search(pattern12, query)
            if match12 and not company_name:
                company_name = match12.group(1).strip()
            
            # 模式13: 包含"给我分析一下"的查询，如"给我分析一下宁德时代的财务状况"
            pattern13 = r'给我分析一下\s*([^0-9（）()\s]+?)(?:\s*的|\s|$)'
            match13 = re.search(pattern13, query)
            if match13 and not company_name:
                company_name = match13.group(1).strip()
            
            # 模式14: 包含"的"字的查询，如"嘉友国际的财务表现如何"
            pattern14 = r'([^0-9（）()\s]+?)\s*的\s*(?:财务表现|盈利能力|现金流状况|资产负债情况|技术面|股价走势|技术指标|技术面表现|估值水平|市盈率|市净率|估值|投资风险|风险因素|风险评估|投资价值|股票|基本面情况|基本面|财务状况)'
            match14 = re.search(pattern14, query)
            if match14 and not company_name:
                company_name = match14.group(1).strip()
            
            # 模式15: 包含"在...中"的查询（无"的"字），如"比亚迪在新能源汽车行业的表现"
            pattern15 = r'([^0-9（）()\s]+?)\s*在\s*[^0-9（）()\s]*\s*中'
            match15 = re.search(pattern15, query)
            if match15 and not company_name:
                company_name = match15.group(1).strip()
            
            # 模式16: 包含"在...中"的查询，如"嘉友国际在行业中的地位"
            pattern16 = r'([^0-9（）()\s]+?)\s*在\s*[^0-9（）()\s]*\s*中\s*的'
            match16 = re.search(pattern16, query)
            if match16 and not company_name:
                company_name = match16.group(1).strip()
            
            # 模式17: 包含"面临"的查询，如"比亚迪面临的主要风险"
            pattern17 = r'([^0-9（）()\s]+?)\s*面临'
            match17 = re.search(pattern17, query)
            if match17 and not company_name:
                company_name = match17.group(1).strip()
            
            # 模式18: 直接包含5-6位数字股票代码
            pattern18 = r'\b(\d{5,6})\b'
            match18 = re.search(pattern18, query)
            if match18:
                stock_code = match18.group(1)
            
            # 模式19: 包含"值得买"的查询，如"603871 这个股票值得买吗"
            pattern19 = r'(\d{5,6})\s*(?:这个|这只)?\s*股票\s*值得买'
            match19 = re.search(pattern19, query)
            if match19 and not stock_code:
                stock_code = match19.group(1)
            
            # 模式20: 包含"这个股票最近表现"的查询，如"603871这个股票最近表现怎么样，值得投资吗"
            pattern20 = r'(\d{5,6})\s*这个\s*股票\s*最近表现'
            match20 = re.search(pattern20, query)
            if match20 and not stock_code:
                stock_code = match20.group(1)
            
            # ========== English Patterns ==========
            # Pattern 21: "Analyze Apple (AAPL)" or "Analyze Apple(AAPL)"
            pattern21 = r'(?:analyze|analysis|please\s+analyze)\s+([A-Za-z\s]+?)\s*[\(（](\d{5,6}|[A-Z]{1,5})[\)）]'
            match21 = re.search(pattern21, query, re.IGNORECASE)
            if match21:
                company_name = match21.group(1).strip()
                stock_code = match21.group(2)
                return company_name, stock_code
            
            # Pattern 22: "Please analyze Tesla stock" or "Analyze Tesla"
            # Require ticker only when clearly indicated (e.g., inside parentheses) to avoid
            # misinterpreting company name substrings (e.g., "Nvidia" → "VIDIA").
            pattern22 = r'(?:please\s+)?(?:analyze|analysis|check|look\s+at)\s+([A-Za-z\s]+?)(?:\s+stock|\s+company|\s+inc\.?|\s+corp\.?)?(?:\s*[\(（](\d{5,6}|[A-Z]{1,5})[\)）])?'
            match22 = re.search(pattern22, query, re.IGNORECASE)
            if match22 and not company_name:
                company_name = match22.group(1).strip()
                if match22.group(2):
                    stock_code = match22.group(2)
            
            # Pattern 23: "What about Apple (AAPL)?" or "Tell me about Tesla"
            pattern23 = r'(?:what\s+about|tell\s+me\s+about|show\s+me|info\s+on)\s+([A-Za-z\s]+?)\s*[\(（]?(\d{5,6}|[A-Z]{1,5})?[\)）]?'
            match23 = re.search(pattern23, query, re.IGNORECASE)
            if match23 and not company_name:
                company_name = match23.group(1).strip()
                if match23.group(2):
                    stock_code = match23.group(2)
            
            # Pattern 24: "Is Apple (AAPL) worth investing?" or "Should I buy Tesla?"
            pattern24 = r'([A-Za-z\s]+?)\s*[\(（]?(\d{5,6}|[A-Z]{1,5})?[\)）]?\s*(?:worth|should|good|invest|buy)'
            match24 = re.search(pattern24, query, re.IGNORECASE)
            if match24 and not company_name:
                company_name = match24.group(1).strip()
                if match24.group(2):
                    stock_code = match24.group(2)
            
            # Pattern 25: Direct format "CompanyName (CODE)" or "CODE CompanyName"
            pattern25 = r'([A-Za-z][A-Za-z\s]+?)\s*[\(（](\d{5,6}|[A-Z]{1,5})[\)）]'
            match25 = re.search(pattern25, query)
            if match25 and not company_name:
                company_name = match25.group(1).strip()
                stock_code = match25.group(2)
            
            # Pattern 26: Stock code first "AAPL Apple" or "600519 茅台"
            pattern26 = r'(\d{5,6}|[A-Z]{1,5})\s+([A-Za-z\u4e00-\u9fff]+)'
            match26 = re.search(pattern26, query)
            if match26 and not stock_code:
                stock_code = match26.group(1)
                if not company_name:
                    company_name = match26.group(2).strip()
            
            # Pattern 27: "Stock code: 600519" or "Code: AAPL"
            pattern27 = r'(?:stock\s+code|code|symbol)[\s:]+(\d{5,6}|[A-Z]{1,5})'
            match27 = re.search(pattern27, query, re.IGNORECASE)
            if match27 and not stock_code:
                stock_code = match27.group(1)
            
            # Pattern 28: English company name only (without code)
            if not company_name:
                # Match English company names (capitalized words or lowercase after analyze/analysis)
                # First try capitalized words
                pattern28a = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b'
                matches28a = re.findall(pattern28a, query)
                # Filter out common English words
                english_stop_words = ['Please', 'Analyze', 'Analysis', 'Check', 'Look', 'Tell', 'Show', 'What', 'About', 'Stock', 'Company', 'Invest', 'Buy', 'Worth', 'Should', 'Good']
                for match in matches28a:
                    if match not in english_stop_words and len(match) > 2:
                        company_name = match
                        break
                
                # If no capitalized word found, try lowercase words after analyze/analysis
                if not company_name:
                    pattern28b = r'(?:analyze|analysis|please\s+analyze)\s+([a-z]+)'
                    match28b = re.search(pattern28b, query, re.IGNORECASE)
                    if match28b:
                        potential_name = match28b.group(1).strip()
                        if potential_name.lower() not in [w.lower() for w in english_stop_words] and len(potential_name) > 2:
                            company_name = potential_name.capitalize()  # Capitalize first letter
            
            # Known name aliases (used for direct hit, fuzzy, and smart lookup)
            well_known = {
                'apple': 'AAPL', 'microsoft': 'MSFT', 'google': 'GOOGL',
                'amazon': 'AMZN', 'tesla': 'TSLA', 'meta': 'META',
                'facebook': 'META', 'nvidia': 'NVDA', 'netflix': 'NFLX',
                'nvda': 'NVDA', 'vidia': 'NVDA'  # defensive aliases
            }

            # If nothing extracted yet, try direct substring hit against well-known names in the query
            if not stock_code:
                query_lower = query.lower()
                for alias, code in well_known.items():
                    if re.search(rf'\b{re.escape(alias)}\b', query_lower):
                        stock_code = code
                        if not company_name:
                            company_name = alias.title()
                        break

            # Smart ticker lookup: Try to find stock code from company name using yfinance
            if company_name and not stock_code:
                try:
                    import yfinance as yf
                    from difflib import get_close_matches
                    company_clean = company_name.strip()
                    company_lower = company_clean.lower()
                    
                    # Generate potential tickers using simple patterns
                    potential_tickers = []
                    
                    # Pattern 1: First word uppercase (e.g., "Apple" -> "APPLE")
                    first_word = company_clean.split()[0].upper()
                    if 1 <= len(first_word) <= 5:
                        potential_tickers.append(first_word)
                    
                    # Pattern 2: Try well-known mappings (minimal set for common cases)
                    if company_lower in well_known:
                        potential_tickers.insert(0, well_known[company_lower])  # Try known mappings first
                    else:
                        # Fuzzy match against known aliases to fix common typos (e.g., "nvida" -> NVDA)
                        close = get_close_matches(company_lower, list(well_known.keys()), n=1, cutoff=0.82)
                        if close:
                            potential_tickers.insert(0, well_known[close[0]])
                    
                    # Try each potential ticker with yfinance
                    for ticker_candidate in potential_tickers:
                        try:
                            test_ticker = yf.Ticker(ticker_candidate)
                            info = test_ticker.info
                            # Verify it's a valid ticker and matches the company
                            if info and info.get('longName'):
                                ticker_name = info.get('longName', '').lower()
                                # Fuzzy match: check if company name words appear in ticker name
                                if (company_lower in ticker_name or 
                                    any(word in ticker_name for word in company_lower.split() if len(word) > 3)):
                                    stock_code = ticker_candidate
                                    logger.info(f"Auto-detected stock code {stock_code} for {company_name}")
                                    break
                        except:
                            continue
                except ImportError:
                    logger.debug("yfinance not available for auto-ticker lookup")
                except Exception as e:
                    logger.debug(f"Auto-ticker lookup failed: {e}")
            
            # 清理公司名称（移除常见的无意义词汇）
            if company_name:
                # 移除中文无意义词汇
                chinese_stop_words = ['的', '这个', '这只', '一下', '看看', '了解', '分析', '帮我', '我想', '给我', '财务状况', '投资价值', '基本面情况', '这只股票', '这个股票']
                for word in chinese_stop_words:
                    company_name = company_name.replace(word, '').strip()
                
                # 移除英文无意义词汇
                english_stop_words = ['the', 'a', 'an', 'this', 'that', 'stock', 'company', 'inc', 'corp', 'ltd', 'please', 'analyze', 'analysis', 'check', 'look', 'tell', 'show', 'what', 'about', 'invest', 'buy', 'worth', 'should', 'good']
                words = company_name.split()
                company_name = ' '.join([w for w in words if w.lower() not in english_stop_words])
                company_name = company_name.strip()
                
                # 如果公司名称太短（少于2个字符），可能是误匹配
                if len(company_name) < 2:
                    company_name = None
            
            return company_name, stock_code

        # 执行提取
        company_name, stock_code = extract_stock_info(user_query)

        # 记录提取结果
        logger.info(f"Extracted from query - Company name: {company_name}, Stock code: {stock_code}")

        # ============================================================================
        # 4. 时间信息处理
        # ============================================================================
        
        # 获取当前时间信息
        current_datetime = datetime.now()
        current_date_cn = current_datetime.strftime("%Y年%m月%d日")
        current_date_en = current_datetime.strftime("%Y-%m-%d")
        current_weekday_cn = ["星期一", "星期二", "星期三", "星期四",
                              "星期五", "星期六", "星期日"][current_datetime.weekday()]
        current_time = current_datetime.strftime("%H:%M:%S")

        # 格式化完整的时间信息
        current_time_info = f"{current_date_cn} ({current_date_en}) {current_weekday_cn} {current_time}"

        logger.info(f"Current time: {current_time_info}")

        # ============================================================================
        # 5. 准备初始状态数据
        # ============================================================================
        
        # 准备初始状态
        initial_data = {
            "query": user_query,
            "current_date": current_date_en,
            "current_date_cn": current_date_cn,
            "current_time": current_time,
            "current_weekday_cn": current_weekday_cn,
            "current_time_info": current_time_info,
            "analysis_timestamp": current_datetime.isoformat()
        }
        
        # 添加公司名称（如果提取到）
        if company_name:
            initial_data["company_name"] = company_name
            
        # 添加股票代码（如果提取到），并添加交易所前缀
        if stock_code:
            # Check if it's a US stock code (1-5 uppercase letters)
            # re module is already imported at the top of the file
            if re.match(r'^[A-Z]{1,5}$', stock_code.upper()):
                # US stock code - use as is (e.g., AAPL, TSLA)
                initial_data["stock_code"] = stock_code.upper()
                initial_data["market"] = "US"
            elif stock_code.startswith('6'):
                # A-share: Shanghai Stock Exchange
                initial_data["stock_code"] = f"sh.{stock_code}"
                initial_data["market"] = "A-share"
            elif stock_code.startswith('0') or stock_code.startswith('3'):
                # A-share: Shenzhen Stock Exchange
                initial_data["stock_code"] = f"sz.{stock_code}"
                initial_data["market"] = "A-share"
            else:
                # Unknown format - try to use as is
                initial_data["stock_code"] = stock_code
                initial_data["market"] = "Unknown"

        # 创建LangGraph工作流的初始状态
        initial_state = AgentState(
            messages=[],  # Langchain约定：消息列表
            data=initial_data,  # 应用特定数据，包含提取的信息
            metadata={}  # 其他运行时特定信息
        )

        # ============================================================================
        # 6. 执行工作流
        # ============================================================================
        
        # 显示分析开始信息
        print(f"\n{WAIT_ICON} Starting financial analysis for '{user_query}'...")
        if company_name:
            print(f"{WAIT_ICON} Company: {company_name}")
        if stock_code:
            print(f"{WAIT_ICON} Stock code: {stock_code}")
        logger.info(
            f"Starting financial analysis workflow for query: '{user_query}'")

        # 显示分析阶段提示（串行执行）
        print(f"\n{WAIT_ICON} Running analysis in sequence (to avoid resource conflicts):")
        print(f"{WAIT_ICON}   1/4 Fundamental analysis...")
        print(f"{WAIT_ICON}   2/4 Technical analysis...")
        print(f"{WAIT_ICON}   3/4 Valuation analysis...")
        print(f"{WAIT_ICON}   4/4 News analysis...")
        print(f"{WAIT_ICON} This may take a few minutes, please wait...\n")

        # 调用工作流 - 这是阻塞调用，会等待所有智能体完成
        final_state = await app.ainvoke(initial_state)
        print(f"{SUCCESS_ICON} Analysis completed!")
        logger.info("Workflow execution completed successfully")

        # ============================================================================
        # 7. 结果处理和报告生成
        # ============================================================================
        
        # 提取并打印最终报告
        if final_state and final_state.get("data") and "final_report" in final_state["data"]:
            print("\n--- Final Analysis Report ---\n")
            # print(final_state["data"]["final_report"])

            # 显示报告文件路径（如果可用）
            if "report_path" in final_state["data"]:
                print(
                    f"\n{SUCCESS_ICON} Report saved to: {final_state['data']['report_path']}")
                logger.info(
                    f"Report saved to: {final_state['data']['report_path']}")

                # 记录最终报告到执行日志
                execution_logger.log_final_report(
                    final_state["data"]["final_report"],
                    final_state["data"]["report_path"]
                )
        else:
            print(f"\n{ERROR_ICON} Error: Could not retrieve final report from workflow.")
            logger.error(
                "Could not retrieve the final report from the workflow")
            print("Debug info - Final state content:", final_state)

        # 完成执行日志记录
        finalize_execution_logger(success=True)
        print(f"{SUCCESS_ICON} Execution log saved to: {execution_logger.execution_dir}")

    except Exception as e:
        # ============================================================================
        # 8. 错误处理
        # ============================================================================
        
        print(f"\n{ERROR_ICON} Error occurred during workflow execution: {e}")
        logger.error(f"Error during workflow execution: {e}", exc_info=True)

        # 记录错误并完成执行日志
        finalize_execution_logger(success=False, error=str(e))
        print(f"{ERROR_ICON} Error log saved to: {get_execution_logger().execution_dir}")


# ============================================================================
# 程序入口点
# ============================================================================

if __name__ == "__main__":
    # 使用asyncio运行主函数
    asyncio.run(main())
