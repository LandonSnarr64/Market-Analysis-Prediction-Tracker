# AI Market Prediction Tracker

This is a Streamlit website for a senior project research tool.

The app uses stock price data, sector ETF data, technical indicators, fundamentals, analyst data, news headlines, and saved prediction evaluation.
If optional API keys are missing, the app still runs with Yahoo Finance data and built-in explanations.

## What the files do

- `app.py` is the website. This is the main file you run.
- `requirements.txt` lists the Python package the project needs.
- `README.md` explains the project and how to run it.
- `supabase_schema.sql` creates the online database tables for deployment.
- `.streamlit/config.toml` stores Streamlit display settings for deployment.
- `.streamlit/secrets.example.toml` shows the secret keys the deployed app can use.

## How to run the app

Open a terminal in this folder and type:

```bash
pip install -r requirements.txt
streamlit run app.py
```

After that, Streamlit should open the website in your browser.

## What the app includes

- One selected stock from each market sector
- Candidate stock comparison inside each sector
- A simulated $1,000 investment in each selected stock
- Real stock price data using `yfinance`
- Sector ETF trend data
- 3 day trend
- 7 day trend
- 20 day moving average comparison
- 50 day moving average comparison
- Volume change
- RSI
- Volatility
- Revenue growth
- Earnings growth
- Profit margin
- Forward P/E
- Analyst target upside
- Recent headline sentiment
- A simulated AI selection label: Top Pick, Watch, or Avoid for Now
- A next 3 day prediction
- A confidence score
- SQLite prediction saving
- Automatic evaluation after the prediction target date passes
- Rolling daily trend predictions versus reality
- Forecasts for today, tomorrow, and the day after
- A 7 forecast date display limit so the page does not get too crowded
- Optional Financial Modeling Prep news with `FMP_API_KEY`
- Optional OpenAI explanations with `OPENAI_API_KEY`

## Optional API keys

The app works without API keys.

To improve the model later, you can add:

- `FMP_API_KEY` for stronger news data
- `OPENAI_API_KEY` for AI-written explanations

## What to do next

Use `DEPLOYMENT.md` to put the app online.
