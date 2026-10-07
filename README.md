# Market Analysis & Prediction Tracker

This project is a financial market tracker I built using Python and Streamlit. I originally started it as my high school senior project because I wanted to learn more about financial markets and explore how data and technology could be used to analyze stocks.

The app compares stocks across different market sectors using real market data, technical indicators, company fundamentals, analyst information, and recent news. It combines these factors into a scoring system and tracks how its predictions compare with actual market results over time.

## What It Does

The tracker looks at several stocks within each market sector and compares them using different types of financial data.

For each stock, it considers:

- Recent price performance
- 20-day and 50-day moving averages
- Trading volume
- RSI
- Volatility
- Revenue and earnings growth
- Profit margins
- Forward P/E
- Analyst price targets
- Sector performance
- Recent news

The program combines these factors into a score and uses that score to identify the strongest stock within each sector and generate a short-term market outlook.

## Prediction Tracking

One of the main goals of the project was to go beyond simply generating a prediction.

The app saves its previous predictions and later compares them with what actually happened in the market. This allows me to track how the system performs over time instead of only looking at its current results.

The dashboard also includes a simulated portfolio to show how the selected stocks perform after being chosen.

## How the Scoring Works

The prediction system uses a scoring method that I designed rather than a trained machine-learning model.

Different factors contribute positively or negatively to a stock's score. For example, the system considers recent price trends, moving averages, company growth, analyst expectations, sector performance, news, and volatility.

The score is then used to compare stocks and create a short-term directional signal.

## Built With

- Python
- Streamlit
- pandas
- yfinance
- Supabase
- Financial Modeling Prep API (optional)
- OpenAI API (optional)

Yahoo Finance provides most of the market and company data used by the application. Additional APIs can be used for news data and explanations, but the main application can still run without them.

## Running the Project

Install the required packages:

```bash
pip install -r requirements.txt
