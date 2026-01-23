# 🧠 Financial Analysis Agent (MCP Multi-Agent System)

## 📘 Overview
**Financial Analysis Agent** is an intelligent multi-agent system designed to automate and streamline stock market analysis.  
Built using the **Model Context Protocol (MCP)**, this project integrates multiple specialized AI agents to analyze financial data, technical indicators, valuation metrics, and news for **U.S. stocks**.

The system delivers a **comprehensive investment summary** by combining the reasoning of different analytical perspectives, enabling data-driven investment insights with minimal manual effort.

---

## 🧩 System Architecture

The system consists of **four key agents**, each responsible for a unique area of analysis:

| Agent | Description |
|--------|--------------|
| 🧮 **Technical Analysis Agent** | Examines stock price trends, momentum, and indicators such as RSI, MACD, and moving averages. |
| 💰 **Value Analysis Agent** | Evaluates financial ratios and valuation metrics (P/E, P/B, DCF) to estimate intrinsic value. |
| 🧾 **Fundamental Analysis Agent** | Reviews company financial statements, earnings reports, and key fundamentals. |
| 🧠 **Summary Agent** | Synthesizes results from all agents to produce a final investment recommendation and rationale. |

Agents communicate through the **MCP framework**, exchanging structured results and reasoning chains to produce cohesive analysis.

---

## ⚙️ Installation

1. **Clone the Repository**
   git clone https://github.com/<your-username>/Financial_Analysis_Agent.git
   cd Financial_Analysis_Agent

2. **Set Up the Environment**
   This project uses **Poetry** for dependency management.
   pip install poetry
   poetry install

3. **Configure Environment Variables**
   Create a `.env` file in the root directory and set your API keys (for OpenAI-compatible models or data sources):
   OPENAI_API_KEY=your_api_key_here

---

## 🚀 Usage

Run the Financial Analysis:
   poetry run python -m src.main --command "Analyze Apple"

Example output:
   ✅ Technical Analysis: Bullish trend with strong RSI momentum
   💰 Valuation: Fairly priced relative to fundamentals
   🧾 Fundamentals: Consistent revenue growth, strong cash flow
   🧠 Summary: BUY recommendation — moderate risk, long-term growth potential

---

## 📂 Project Structure

Financial_Analysis_Agent/
│
├── src/
│   ├── agents/                # Core analysis agents (technical, value, fundamental, summary)
│   ├── data/                  # Data collection and preprocessing
│   ├── utils/                 # Helper utilities
│   └── main.py                # Entry point orchestrating all agents
│
├── pyproject.toml             # Poetry configuration
├── .env.example               # Example of required environment variables
└── README.md                  # Project documentation

---

## 📈 Features

- ✅ Modular multi-agent design using MCP  
- ✅ Extensible architecture — easily add new agents or data sources  
- ✅ Integrates real-time financial and market data  
- ✅ Generates explainable investment summaries  

---

## 🧠 Future Improvements

- Add support for **international markets**  
- Integrate **sentiment analysis** from financial news and social media  
- Build a **web dashboard** for interactive visualization  
- Implement **backtesting and performance tracking**  

---

## 🪪 License
Released under the **MIT License**.  
You are free to use, modify, and distribute this project with attribution.
