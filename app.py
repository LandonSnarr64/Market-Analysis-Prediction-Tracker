import json
import os
import sqlite3
from datetime import date, timedelta

import pandas as pd
import requests
import streamlit as st
import yfinance as yf
from openai import OpenAI
from supabase import create_client


st.set_page_config(
    page_title="Market Analysis & Prediction Tracker",
    page_icon=":chart_with_upwards_trend:",
    layout="wide",
)


SECTORS = [
    {
        "sector": "Technology",
        "sector_etf": "XLK",
        "candidates": {
            "AAPL": "Apple",
            "MSFT": "Microsoft",
            "NVDA": "Nvidia",
        },
    },
    {
        "sector": "Healthcare",
        "sector_etf": "XLV",
        "candidates": {
            "JNJ": "Johnson & Johnson",
            "UNH": "UnitedHealth Group",
            "LLY": "Eli Lilly",
        },
    },
    {
        "sector": "Financials",
        "sector_etf": "XLF",
        "candidates": {
            "JPM": "JPMorgan Chase",
            "BAC": "Bank of America",
            "GS": "Goldman Sachs",
        },
    },
    {
        "sector": "Energy",
        "sector_etf": "XLE",
        "candidates": {
            "XOM": "Exxon Mobil",
            "CVX": "Chevron",
            "SLB": "SLB",
        },
    },
    {
        "sector": "Consumer Discretionary",
        "sector_etf": "XLY",
        "candidates": {
            "AMZN": "Amazon",
            "TSLA": "Tesla",
            "HD": "Home Depot",
        },
    },
    {
        "sector": "Industrials",
        "sector_etf": "XLI",
        "candidates": {
            "CAT": "Caterpillar",
            "GE": "GE Aerospace",
            "HON": "Honeywell",
        },
    },
]


DB_PATH = "predictions.db"
STARTING_PORTFOLIO_VALUE = 6000
INVESTMENT_PER_PICK = 1000


POSITIVE_NEWS_WORDS = [
    "beat",
    "beats",
    "growth",
    "upgrade",
    "upgraded",
    "strong",
    "record",
    "profit",
    "profits",
    "surge",
    "rally",
    "gain",
    "gains",
    "bullish",
    "outperform",
    "raises",
    "partnership",
    "expands",
    "approval",
]


NEGATIVE_NEWS_WORDS = [
    "miss",
    "misses",
    "drop",
    "drops",
    "fall",
    "falls",
    "lawsuit",
    "probe",
    "cut",
    "cuts",
    "downgrade",
    "downgraded",
    "weak",
    "loss",
    "losses",
    "bearish",
    "underperform",
    "warning",
    "recall",
    "investigation",
]


def get_config_value(name):
    """Read an optional key from Streamlit secrets or computer environment variables."""
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass

    return os.getenv(name)


def calculate_percent_change(new_value, old_value):
    """Calculate percent change between two numbers."""
    if old_value == 0:
        return 0

    return (new_value - old_value) / old_value * 100


def calculate_rsi(close_prices):
    """Calculate a 14 day RSI."""
    price_changes = close_prices.diff()
    gains = price_changes.clip(lower=0)
    losses = -price_changes.clip(upper=0)

    average_gain = gains.rolling(window=14).mean().iloc[-1]
    average_loss = losses.rolling(window=14).mean().iloc[-1]

    if average_loss == 0:
        return 100

    relative_strength = average_gain / average_loss
    return 100 - (100 / (1 + relative_strength))


def clamp(value, lowest, highest):
    """Keep a number inside a minimum and maximum range."""
    return max(lowest, min(value, highest))


def safe_number(value, default=0):
    """Convert missing or messy finance values into usable numbers."""
    if value is None:
        return default

    try:
        return float(value)
    except Exception:
        return default


def get_database_backend():
    """Use Supabase online when keys exist; otherwise use local SQLite."""
    supabase_url = get_config_value("SUPABASE_URL")
    supabase_key = get_config_value("SUPABASE_KEY")

    if supabase_url and supabase_key:
        return "supabase"

    return "sqlite"


@st.cache_resource
def get_supabase_client():
    """Connect to Supabase for hosted database storage."""
    supabase_url = get_config_value("SUPABASE_URL")
    supabase_key = get_config_value("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        return None

    return create_client(supabase_url, supabase_key)


def init_database():
    """Create the SQLite table if it does not exist yet."""
    if get_database_backend() == "supabase":
        return

    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prediction_date TEXT NOT NULL,
            target_date TEXT NOT NULL,
            sector TEXT NOT NULL,
            ticker TEXT NOT NULL,
            company_name TEXT NOT NULL,
            selected_price REAL NOT NULL,
            model_score REAL NOT NULL,
            signal TEXT NOT NULL,
            prediction TEXT NOT NULL,
            confidence INTEGER NOT NULL,
            candidate_scores TEXT NOT NULL,
            data_snapshot TEXT NOT NULL,
            result_status TEXT DEFAULT 'Pending',
            result_return REAL,
            result_price REAL,
            UNIQUE(prediction_date, sector)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_forecasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prediction_date TEXT NOT NULL,
            forecast_date TEXT NOT NULL,
            horizon_days INTEGER NOT NULL,
            sector TEXT NOT NULL,
            ticker TEXT NOT NULL,
            company_name TEXT NOT NULL,
            starting_price REAL NOT NULL,
            predicted_direction TEXT NOT NULL,
            confidence INTEGER NOT NULL,
            model_score REAL NOT NULL,
            actual_direction TEXT DEFAULT 'Pending',
            actual_return REAL,
            actual_price REAL,
            result_status TEXT DEFAULT 'Pending',
            UNIQUE(prediction_date, forecast_date, sector, ticker)
        )
        """
    )

    connection.commit()
    connection.close()


def save_today_predictions(best_picks, all_candidates_by_sector):
    """Save today's selected stock for each sector."""
    if get_database_backend() == "supabase":
        save_today_predictions_supabase(best_picks, all_candidates_by_sector)
        return

    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()
    today = date.today()
    target_date = today + timedelta(days=3)

    for pick in best_picks:
        candidates = all_candidates_by_sector[pick["sector"]]
        candidate_scores = [
            {
                "ticker": candidate["ticker"],
                "company_name": candidate["company_name"],
                "score": candidate["score"],
                "prediction": candidate["prediction"],
                "confidence": candidate["confidence"],
            }
            for candidate in candidates
        ]

        data_snapshot = {
            "stock_data": pick["stock_data"],
            "sector_data": pick["sector_data"],
            "fundamental_data": pick["fundamental_data"],
            "news_score": pick["news_data"]["news_score"],
            "headlines": pick["news_data"]["headlines"],
        }

        cursor.execute(
            """
            INSERT OR REPLACE INTO predictions (
                prediction_date,
                target_date,
                sector,
                ticker,
                company_name,
                selected_price,
                model_score,
                signal,
                prediction,
                confidence,
                candidate_scores,
                data_snapshot,
                result_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pending')
            """,
            (
                today.isoformat(),
                target_date.isoformat(),
                pick["sector"],
                pick["ticker"],
                pick["company_name"],
                pick["stock_data"]["current_price"],
                pick["score"],
                pick["signal"],
                pick["prediction"],
                pick["confidence"],
                json.dumps(candidate_scores, default=str),
                json.dumps(data_snapshot, default=str),
            ),
        )

    connection.commit()
    connection.close()


def save_today_predictions_supabase(best_picks, all_candidates_by_sector):
    """Save today's selected stock for each sector in Supabase."""
    supabase = get_supabase_client()

    if supabase is None:
        return

    today = date.today()
    target_date = today + timedelta(days=3)
    rows = []

    for pick in best_picks:
        candidates = all_candidates_by_sector[pick["sector"]]
        candidate_scores = [
            {
                "ticker": candidate["ticker"],
                "company_name": candidate["company_name"],
                "score": candidate["score"],
                "prediction": candidate["prediction"],
                "confidence": candidate["confidence"],
            }
            for candidate in candidates
        ]

        data_snapshot = {
            "stock_data": pick["stock_data"],
            "sector_data": pick["sector_data"],
            "fundamental_data": pick["fundamental_data"],
            "news_score": pick["news_data"]["news_score"],
            "headlines": pick["news_data"]["headlines"],
        }

        rows.append(
            {
                "prediction_date": today.isoformat(),
                "target_date": target_date.isoformat(),
                "sector": pick["sector"],
                "ticker": pick["ticker"],
                "company_name": pick["company_name"],
                "selected_price": float(pick["stock_data"]["current_price"]),
                "model_score": float(pick["score"]),
                "signal": pick["signal"],
                "prediction": pick["prediction"],
                "confidence": int(pick["confidence"]),
                "candidate_scores": candidate_scores,
                "data_snapshot": data_snapshot,
                "result_status": "Pending",
            }
        )

    supabase.table("predictions").upsert(
        rows,
        on_conflict="prediction_date,sector",
    ).execute()


def get_daily_prediction(score, horizon_days):
    """Predict Up, Down, or Flat for a specific future day."""
    horizon_penalty = (horizon_days - 1) * 0.75
    adjusted_score = score - horizon_penalty

    if adjusted_score >= 3:
        return "Up"

    if adjusted_score <= -3:
        return "Down"

    return "Flat"


def save_daily_forecasts(best_picks):
    """Save daily forecasts for today, tomorrow, and the next day."""
    if get_database_backend() == "supabase":
        save_daily_forecasts_supabase(best_picks)
        return

    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()
    today = date.today()

    for pick in best_picks:
        for horizon_days in [0, 1, 2]:
            forecast_date = today + timedelta(days=horizon_days)

            cursor.execute(
                """
                INSERT OR REPLACE INTO daily_forecasts (
                    prediction_date,
                    forecast_date,
                    horizon_days,
                    sector,
                    ticker,
                    company_name,
                    starting_price,
                    predicted_direction,
                    confidence,
                    model_score,
                    actual_direction,
                    result_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pending', 'Pending')
                """,
                (
                    today.isoformat(),
                    forecast_date.isoformat(),
                    horizon_days,
                    pick["sector"],
                    pick["ticker"],
                    pick["company_name"],
                    pick["stock_data"]["current_price"],
                    get_daily_prediction(pick["score"], horizon_days),
                    pick["confidence"],
                    pick["score"],
                ),
            )

    connection.commit()
    connection.close()
    trim_daily_forecasts()


def save_daily_forecasts_supabase(best_picks):
    """Save daily forecasts in Supabase."""
    supabase = get_supabase_client()

    if supabase is None:
        return

    today = date.today()
    rows = []

    for pick in best_picks:
        for horizon_days in [0, 1, 2]:
            forecast_date = today + timedelta(days=horizon_days)
            rows.append(
                {
                    "prediction_date": today.isoformat(),
                    "forecast_date": forecast_date.isoformat(),
                    "horizon_days": horizon_days,
                    "sector": pick["sector"],
                    "ticker": pick["ticker"],
                    "company_name": pick["company_name"],
                    "starting_price": float(pick["stock_data"]["current_price"]),
                    "predicted_direction": get_daily_prediction(pick["score"], horizon_days),
                    "confidence": int(pick["confidence"]),
                    "model_score": float(pick["score"]),
                    "actual_direction": "Pending",
                    "result_status": "Pending",
                }
            )

    supabase.table("daily_forecasts").upsert(
        rows,
        on_conflict="prediction_date,forecast_date,sector,ticker",
    ).execute()
    trim_daily_forecasts_supabase()


def trim_daily_forecasts():
    """Keep only the most recent 7 forecast dates for each sector."""
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute(
        """
        DELETE FROM daily_forecasts
        WHERE id NOT IN (
            SELECT id
            FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY sector
                           ORDER BY forecast_date DESC, prediction_date DESC
                       ) AS row_number
                FROM daily_forecasts
            )
            WHERE row_number <= 7
        )
        """
    )

    connection.commit()
    connection.close()


def trim_daily_forecasts_supabase():
    """Keep Supabase forecast history manageable."""
    supabase = get_supabase_client()

    if supabase is None:
        return

    for sector in [item["sector"] for item in SECTORS]:
        response = (
            supabase.table("daily_forecasts")
            .select("id")
            .eq("sector", sector)
            .order("forecast_date", desc=True)
            .order("prediction_date", desc=True)
            .execute()
        )
        rows_to_delete = response.data[7:]

        for row in rows_to_delete:
            supabase.table("daily_forecasts").delete().eq("id", row["id"]).execute()


@st.cache_data(ttl=900)
def get_actual_day_move(ticker, forecast_date_text):
    """Compare the forecast date close against the previous trading close."""
    try:
        forecast_day = date.fromisoformat(forecast_date_text)
        start_day = forecast_day - timedelta(days=10)
        end_day = forecast_day + timedelta(days=5)
        price_history = yf.Ticker(ticker).history(
            start=start_day.isoformat(),
            end=end_day.isoformat(),
        )

        if len(price_history) < 2:
            return None

        price_history = price_history.reset_index()
        price_history["DateOnly"] = pd.to_datetime(price_history["Date"]).dt.date
        matching_rows = price_history[price_history["DateOnly"] >= forecast_day]

        if matching_rows.empty:
            return None

        forecast_index = matching_rows.index[0]

        if forecast_index == 0:
            return None

        previous_close = price_history.loc[forecast_index - 1, "Close"]
        actual_price = price_history.loc[forecast_index, "Close"]
        actual_return = calculate_percent_change(actual_price, previous_close)

        if actual_return > 0.2:
            actual_direction = "Up"
        elif actual_return < -0.2:
            actual_direction = "Down"
        else:
            actual_direction = "Flat"

        return {
            "actual_direction": actual_direction,
            "actual_return": actual_return,
            "actual_price": actual_price,
        }

    except Exception:
        return None


def daily_prediction_was_correct(predicted_direction, actual_direction):
    """Decide whether the predicted direction matched reality."""
    return predicted_direction == actual_direction


def evaluate_daily_forecasts():
    """Fill in actual results for daily forecasts when market data is available."""
    if get_database_backend() == "supabase":
        evaluate_daily_forecasts_supabase()
        return

    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()
    today = date.today().isoformat()

    cursor.execute(
        """
        SELECT id, ticker, forecast_date, predicted_direction
        FROM daily_forecasts
        WHERE result_status = 'Pending'
        AND forecast_date <= ?
        """,
        (today,),
    )

    rows = cursor.fetchall()

    for forecast_id, ticker, forecast_date_text, predicted_direction in rows:
        actual_move = get_actual_day_move(ticker, forecast_date_text)

        if actual_move is None:
            continue

        if daily_prediction_was_correct(
            predicted_direction,
            actual_move["actual_direction"],
        ):
            result_status = "Correct"
        else:
            result_status = "Incorrect"

        cursor.execute(
            """
            UPDATE daily_forecasts
            SET actual_direction = ?,
                actual_return = ?,
                actual_price = ?,
                result_status = ?
            WHERE id = ?
            """,
            (
                actual_move["actual_direction"],
                actual_move["actual_return"],
                actual_move["actual_price"],
                result_status,
                forecast_id,
            ),
        )

    connection.commit()
    connection.close()


def evaluate_daily_forecasts_supabase():
    """Fill in actual daily forecast results in Supabase."""
    supabase = get_supabase_client()

    if supabase is None:
        return

    today = date.today().isoformat()
    response = (
        supabase.table("daily_forecasts")
        .select("id,ticker,forecast_date,predicted_direction")
        .eq("result_status", "Pending")
        .lte("forecast_date", today)
        .execute()
    )

    for row in response.data:
        actual_move = get_actual_day_move(row["ticker"], row["forecast_date"])

        if actual_move is None:
            continue

        if daily_prediction_was_correct(
            row["predicted_direction"],
            actual_move["actual_direction"],
        ):
            result_status = "Correct"
        else:
            result_status = "Incorrect"

        supabase.table("daily_forecasts").update(
            {
                "actual_direction": actual_move["actual_direction"],
                "actual_return": float(actual_move["actual_return"]),
                "actual_price": float(actual_move["actual_price"]),
                "result_status": result_status,
            }
        ).eq("id", row["id"]).execute()


def load_daily_forecasts():
    """Load the rolling daily forecast table."""
    if get_database_backend() == "supabase":
        return load_daily_forecasts_supabase()

    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT forecast_date,
               sector,
               ticker,
               company_name,
               predicted_direction,
               actual_direction,
               result_status,
               actual_return,
               confidence
        FROM daily_forecasts
        ORDER BY forecast_date DESC, sector
        LIMIT 42
        """
    )

    rows = cursor.fetchall()
    connection.close()
    return rows


def load_daily_forecasts_supabase():
    """Load rolling daily forecasts from Supabase."""
    supabase = get_supabase_client()

    if supabase is None:
        return []

    response = (
        supabase.table("daily_forecasts")
        .select(
            "forecast_date,sector,ticker,company_name,predicted_direction,"
            "actual_direction,result_status,actual_return,confidence"
        )
        .order("forecast_date", desc=True)
        .order("sector")
        .limit(42)
        .execute()
    )

    return [
        (
            row["forecast_date"],
            row["sector"],
            row["ticker"],
            row["company_name"],
            row["predicted_direction"],
            row["actual_direction"],
            row["result_status"],
            row["actual_return"],
            row["confidence"],
        )
        for row in response.data
    ]


def prediction_was_correct(prediction, result_return):
    """Check whether a prediction matched the later price move."""
    if prediction == "Likely Up":
        return result_return > 0

    if prediction == "Slightly Up or Flat":
        return result_return >= -0.5

    if prediction == "Flat or Unclear":
        return abs(result_return) <= 1

    if prediction == "Likely Down":
        return result_return < 0

    return False


def evaluate_old_predictions():
    """Mark predictions correct or incorrect once their target date arrives."""
    if get_database_backend() == "supabase":
        evaluate_old_predictions_supabase()
        return

    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()
    today = date.today().isoformat()

    cursor.execute(
        """
        SELECT id, ticker, selected_price, prediction
        FROM predictions
        WHERE result_status = 'Pending'
        AND target_date <= ?
        """,
        (today,),
    )

    rows = cursor.fetchall()

    for prediction_id, ticker, selected_price, prediction in rows:
        latest_data = get_market_data(ticker)
        result_price = latest_data["current_price"]
        result_return = calculate_percent_change(result_price, selected_price)

        if prediction_was_correct(prediction, result_return):
            result_status = "Correct"
        else:
            result_status = "Incorrect"

        cursor.execute(
            """
            UPDATE predictions
            SET result_status = ?,
                result_return = ?,
                result_price = ?
            WHERE id = ?
            """,
            (result_status, result_return, result_price, prediction_id),
        )

    connection.commit()
    connection.close()


def evaluate_old_predictions_supabase():
    """Mark 3 day predictions correct or incorrect in Supabase."""
    supabase = get_supabase_client()

    if supabase is None:
        return

    today = date.today().isoformat()
    response = (
        supabase.table("predictions")
        .select("id,ticker,selected_price,prediction")
        .eq("result_status", "Pending")
        .lte("target_date", today)
        .execute()
    )

    for row in response.data:
        latest_data = get_market_data(row["ticker"])
        result_price = latest_data["current_price"]
        result_return = calculate_percent_change(result_price, row["selected_price"])

        if prediction_was_correct(row["prediction"], result_return):
            result_status = "Correct"
        else:
            result_status = "Incorrect"

        supabase.table("predictions").update(
            {
                "result_status": result_status,
                "result_return": float(result_return),
                "result_price": float(result_price),
            }
        ).eq("id", row["id"]).execute()


def load_prediction_history():
    """Load saved prediction history for display."""
    if get_database_backend() == "supabase":
        return load_prediction_history_supabase()

    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT prediction_date, target_date, sector, ticker, company_name,
               selected_price, model_score, prediction, confidence,
               result_status, result_return
        FROM predictions
        ORDER BY prediction_date DESC, sector
        LIMIT 60
        """
    )

    rows = cursor.fetchall()
    connection.close()
    return rows


def load_prediction_history_supabase():
    """Load prediction history from Supabase."""
    supabase = get_supabase_client()

    if supabase is None:
        return []

    response = (
        supabase.table("predictions")
        .select(
            "prediction_date,target_date,sector,ticker,company_name,selected_price,"
            "model_score,prediction,confidence,result_status,result_return"
        )
        .order("prediction_date", desc=True)
        .order("sector")
        .limit(60)
        .execute()
    )

    return [
        (
            row["prediction_date"],
            row["target_date"],
            row["sector"],
            row["ticker"],
            row["company_name"],
            row["selected_price"],
            row["model_score"],
            row["prediction"],
            row["confidence"],
            row["result_status"],
            row["result_return"],
        )
        for row in response.data
    ]


def get_news_sentiment_score(headlines):
    """Score headlines using a simple word list."""
    score = 0

    for headline in headlines:
        headline_lower = headline.lower()

        for word in POSITIVE_NEWS_WORDS:
            if word in headline_lower:
                score = score + 1

        for word in NEGATIVE_NEWS_WORDS:
            if word in headline_lower:
                score = score - 1

    return clamp(score, -4, 4)


def get_news_headline(item):
    """Yahoo Finance news data can store the headline in different places."""
    if "title" in item:
        return item["title"]

    if "content" in item and "title" in item["content"]:
        return item["content"]["title"]

    return ""


@st.cache_data(ttl=900)
def get_fmp_news(ticker):
    """Use Financial Modeling Prep news if the user adds an API key."""
    api_key = get_config_value("FMP_API_KEY")

    if not api_key:
        return []

    try:
        url = "https://financialmodelingprep.com/api/v3/stock_news"
        response = requests.get(
            url,
            params={"tickers": ticker, "limit": 5, "apikey": api_key},
            timeout=10,
        )
        response.raise_for_status()
        news_items = response.json()

        return [
            item["title"]
            for item in news_items
            if isinstance(item, dict) and item.get("title")
        ]

    except Exception:
        return []


@st.cache_data(ttl=900)
def get_yahoo_news(ticker):
    """Get Yahoo Finance headlines."""
    try:
        news_items = yf.Ticker(ticker).news[:5]
        headlines = []

        for item in news_items:
            headline = get_news_headline(item)

            if headline:
                headlines.append(headline)

        return headlines

    except Exception:
        return []


@st.cache_data(ttl=900)
def get_news_data(ticker):
    """Get recent headlines from the best available source."""
    fmp_headlines = get_fmp_news(ticker)

    if fmp_headlines:
        headlines = fmp_headlines
        news_source = "Financial Modeling Prep news"
    else:
        headlines = get_yahoo_news(ticker)
        news_source = "Yahoo Finance headlines"

    return {
        "headlines": headlines,
        "news_score": get_news_sentiment_score(headlines),
        "news_source": news_source,
    }


@st.cache_data(ttl=900)
def get_fundamental_data(ticker):
    """Get valuation, growth, earnings, and analyst data where available."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        revenue_growth = safe_number(info.get("revenueGrowth"))
        earnings_growth = safe_number(info.get("earningsGrowth"))
        profit_margin = safe_number(info.get("profitMargins"))
        forward_pe = safe_number(info.get("forwardPE"))
        market_cap = safe_number(info.get("marketCap"))
        recommendation_mean = safe_number(info.get("recommendationMean"), 3)
        target_mean_price = safe_number(info.get("targetMeanPrice"))
        current_price = safe_number(info.get("currentPrice"))

        if current_price > 0 and target_mean_price > 0:
            analyst_upside = calculate_percent_change(target_mean_price, current_price)
        else:
            analyst_upside = 0

        return {
            "revenue_growth": revenue_growth,
            "earnings_growth": earnings_growth,
            "profit_margin": profit_margin,
            "forward_pe": forward_pe,
            "market_cap": market_cap,
            "recommendation_mean": recommendation_mean,
            "analyst_upside": analyst_upside,
            "data_source": "Yahoo Finance fundamentals",
        }

    except Exception:
        return {
            "revenue_growth": 0,
            "earnings_growth": 0,
            "profit_margin": 0,
            "forward_pe": 0,
            "market_cap": 0,
            "recommendation_mean": 3,
            "analyst_upside": 0,
            "data_source": "Backup neutral fundamentals",
        }


@st.cache_data(ttl=900)
def get_market_data(ticker):
    """Get price, volume, and technical data for one ticker."""
    try:
        price_history = yf.Ticker(ticker).history(period="3mo")

        if len(price_history) < 50:
            raise ValueError("Not enough price data was returned.")

        current_price = price_history["Close"].iloc[-1]
        price_three_days_ago = price_history["Close"].iloc[-4]
        price_seven_days_ago = price_history["Close"].iloc[-8]

        three_day_trend = calculate_percent_change(current_price, price_three_days_ago)
        seven_day_trend = calculate_percent_change(current_price, price_seven_days_ago)

        moving_average_20 = price_history["Close"].tail(20).mean()
        moving_average_50 = price_history["Close"].tail(50).mean()
        ma_20_gap = calculate_percent_change(current_price, moving_average_20)
        ma_50_gap = calculate_percent_change(current_price, moving_average_50)

        current_volume = price_history["Volume"].iloc[-1]
        average_volume = price_history["Volume"].tail(20).mean()
        volume_change = calculate_percent_change(current_volume, average_volume)

        daily_returns = price_history["Close"].pct_change().dropna()
        volatility = daily_returns.tail(20).std() * 100

        return {
            "current_price": current_price,
            "three_day_trend": three_day_trend,
            "seven_day_trend": seven_day_trend,
            "ma_20_gap": ma_20_gap,
            "ma_50_gap": ma_50_gap,
            "volume_change": volume_change,
            "rsi": calculate_rsi(price_history["Close"]),
            "volatility": volatility,
            "data_source": "Yahoo Finance market data",
        }

    except Exception:
        return {
            "current_price": 100,
            "three_day_trend": 0,
            "seven_day_trend": 0,
            "ma_20_gap": 0,
            "ma_50_gap": 0,
            "volume_change": 0,
            "rsi": 50,
            "volatility": 2,
            "data_source": "Backup neutral market data",
        }


def score_stock(stock_data, sector_data, news_data, fundamental_data):
    """Build a multi-factor score from technicals, sector trend, news, and fundamentals."""
    score = 0

    score = score + clamp(stock_data["three_day_trend"] * 0.8, -2, 2)
    score = score + clamp(stock_data["seven_day_trend"] * 0.6, -2, 2)
    score = score + clamp(stock_data["ma_20_gap"] * 0.4, -2, 2)
    score = score + clamp(stock_data["ma_50_gap"] * 0.25, -2, 2)
    score = score + clamp(stock_data["volume_change"] * 0.03, -1.5, 1.5)
    score = score + clamp(sector_data["seven_day_trend"] * 0.35, -1.5, 1.5)
    score = score + news_data["news_score"]

    score = score + clamp(fundamental_data["revenue_growth"] * 4, -1.5, 1.5)
    score = score + clamp(fundamental_data["earnings_growth"] * 3, -1.5, 1.5)
    score = score + clamp(fundamental_data["profit_margin"] * 3, -1, 1.5)
    score = score + clamp(fundamental_data["analyst_upside"] * 0.08, -2, 2)

    if 0 < fundamental_data["forward_pe"] < 45:
        score = score + 0.5
    elif fundamental_data["forward_pe"] >= 80:
        score = score - 1

    if fundamental_data["recommendation_mean"] <= 2:
        score = score + 1
    elif fundamental_data["recommendation_mean"] >= 4:
        score = score - 1

    if 45 <= stock_data["rsi"] <= 65:
        score = score + 1
    elif stock_data["rsi"] > 75 or stock_data["rsi"] < 25:
        score = score - 1.5

    if stock_data["volatility"] > 4:
        score = score - 1

    return round(score, 2)


def get_ai_signal(score):
    """Turn the numeric score into a dashboard label."""
    if score >= 7:
        return "Top Pick"
    if score >= 3:
        return "Watch"
    return "Avoid for Now"


def get_next_3_day_prediction(score):
    """Turn the score into a 3 day prediction."""
    if score >= 7:
        return "Likely Up"
    if score >= 3:
        return "Slightly Up or Flat"
    if score > -2:
        return "Flat or Unclear"
    return "Likely Down"


def get_confidence(score):
    """Create a confidence number from the strength of the score."""
    confidence = 45 + abs(score) * 5
    return round(min(confidence, 92))


def get_rule_based_explanation(company_name, sector_name, stock_data, sector_data, news_data, fundamental_data):
    """Create a clear explanation for why the model scored the stock this way."""
    strengths = []
    risks = []

    if stock_data["seven_day_trend"] > 0:
        strengths.append("positive 7 day price trend")
    else:
        risks.append("negative 7 day price trend")

    if stock_data["ma_20_gap"] > 0:
        strengths.append("price above the 20 day moving average")
    else:
        risks.append("price below the 20 day moving average")

    if sector_data["seven_day_trend"] > 0:
        strengths.append(f"the {sector_name} sector is also trending up")
    else:
        risks.append(f"the {sector_name} sector is trending down")

    if news_data["news_score"] > 0:
        strengths.append("recent headlines look positive")
    elif news_data["news_score"] < 0:
        risks.append("recent headlines look negative")

    if fundamental_data["revenue_growth"] > 0:
        strengths.append("revenue growth is positive")
    elif fundamental_data["revenue_growth"] < 0:
        risks.append("revenue growth is negative")

    if fundamental_data["analyst_upside"] > 5:
        strengths.append("analyst target prices suggest upside")
    elif fundamental_data["analyst_upside"] < -5:
        risks.append("analyst target prices suggest downside")

    if stock_data["volatility"] > 4:
        risks.append("recent volatility is high")

    if not strengths:
        strengths.append("some indicators are stable")

    if not risks:
        risks.append("no major short-term risk flags appeared in this model")

    return (
        f"{company_name} was selected for {sector_name} because of "
        f"{', '.join(strengths[:4])}. Main risk factors: {', '.join(risks[:3])}."
    )


@st.cache_data(ttl=900)
def get_openai_explanation(company_name, sector_name, signal, prediction, score, stock_data, sector_data, news_data, fundamental_data):
    """Use OpenAI for a stronger explanation if an API key is available."""
    api_key = get_config_value("OPENAI_API_KEY")

    if not api_key:
        return ""

    try:
        client = OpenAI(api_key=api_key)
        prompt = f"""
        Explain this simulated stock selection in 4 concise sentences.
        Do not give financial advice. Do not tell the user to buy or sell.

        Company: {company_name}
        Sector: {sector_name}
        Label: {signal}
        Next 3 day prediction: {prediction}
        Model score: {score}
        Technical data: {stock_data}
        Sector data: {sector_data}
        Fundamental data: {fundamental_data}
        News score: {news_data["news_score"]}
        Headlines: {news_data["headlines"]}
        """

        response = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
        )

        return response.output_text

    except Exception:
        return ""


def get_explanation(company_name, sector_name, signal, prediction, score, stock_data, sector_data, news_data, fundamental_data):
    """Use OpenAI if available; otherwise use the built-in explanation."""
    openai_explanation = get_openai_explanation(
        company_name,
        sector_name,
        signal,
        prediction,
        score,
        stock_data,
        sector_data,
        news_data,
        fundamental_data,
    )

    if openai_explanation:
        return openai_explanation

    return get_rule_based_explanation(
        company_name,
        sector_name,
        stock_data,
        sector_data,
        news_data,
        fundamental_data,
    )


def analyze_candidate(ticker, company_name, sector_name, sector_etf):
    """Collect all data for one stock and calculate its model result."""
    stock_data = get_market_data(ticker)
    sector_data = get_market_data(sector_etf)
    news_data = get_news_data(ticker)
    fundamental_data = get_fundamental_data(ticker)
    score = score_stock(stock_data, sector_data, news_data, fundamental_data)

    return {
        "ticker": ticker,
        "company_name": company_name,
        "sector": sector_name,
        "sector_etf": sector_etf,
        "stock_data": stock_data,
        "sector_data": sector_data,
        "news_data": news_data,
        "fundamental_data": fundamental_data,
        "score": score,
        "signal": get_ai_signal(score),
        "prediction": get_next_3_day_prediction(score),
        "confidence": get_confidence(score),
    }


def get_best_pick_for_sector(sector):
    """Score every candidate in a sector and return the best one."""
    candidates = []

    for ticker, company_name in sector["candidates"].items():
        candidates.append(
            analyze_candidate(
                ticker,
                company_name,
                sector["sector"],
                sector["sector_etf"],
            )
        )

    return max(candidates, key=lambda candidate: candidate["score"]), candidates


init_database()
evaluate_old_predictions()
evaluate_daily_forecasts()


st.title("Market Analysis & Prediction Tracker")
st.caption("Multi-factor stock analysis using market data, company fundamentals, sector performance, news, and historical prediction tracking.")
st.caption(f"Database mode: {get_database_backend()}")

st.header("Simulated Portfolio")
st.write(
    "The tracker selects one stock from each sector and starts with a simulated $1,000 in each selected stock."
)

best_picks = []
all_candidates_by_sector = {}

with st.spinner("Loading market data, fundamentals, analyst data, and news..."):
    for sector in SECTORS:
        best_pick, candidates = get_best_pick_for_sector(sector)
        best_picks.append(best_pick)
        all_candidates_by_sector[sector["sector"]] = candidates

save_today_predictions(best_picks, all_candidates_by_sector)
save_daily_forecasts(best_picks)
evaluate_daily_forecasts()

total_simulated_value = 0

for pick in best_picks:
    three_day_trend = pick["stock_data"]["three_day_trend"]
    simulated_value = INVESTMENT_PER_PICK * (1 + three_day_trend / 100)
    total_simulated_value = total_simulated_value + simulated_value

portfolio_change = total_simulated_value - STARTING_PORTFOLIO_VALUE
portfolio_change_percent = portfolio_change / STARTING_PORTFOLIO_VALUE * 100

col1, col2, col3 = st.columns(3)
col1.metric("Starting Value", f"${STARTING_PORTFOLIO_VALUE:,.2f}")
col2.metric("Current Simulated Value", f"${total_simulated_value:,.2f}")
col3.metric("Simulated Change", f"${portfolio_change:,.2f}", f"{portfolio_change_percent:.2f}%")

st.header("Selected Stocks")

for pick in best_picks:
    stock_data = pick["stock_data"]
    sector_data = pick["sector_data"]
    news_data = pick["news_data"]
    fundamental_data = pick["fundamental_data"]
    simulated_value = INVESTMENT_PER_PICK * (1 + stock_data["three_day_trend"] / 100)
    explanation = get_explanation(
        pick["company_name"],
        pick["sector"],
        pick["signal"],
        pick["prediction"],
        pick["score"],
        stock_data,
        sector_data,
        news_data,
        fundamental_data,
    )

    with st.container(border=True):
        top_left, top_right = st.columns([2, 1])

        with top_left:
            st.subheader(f"{pick['sector']}: {pick['company_name']} ({pick['ticker']})")
            st.write(f"Sector ETF tracked: {pick['sector_etf']}")
            st.write(explanation)

        with top_right:
            st.metric("Current Stock Price", f"${stock_data['current_price']:.2f}")
            st.metric("Model Score", pick["score"])

        prediction_cols = st.columns(4)
        prediction_cols[0].write("**Signal**")
        prediction_cols[0].write(pick["signal"])

        prediction_cols[1].write("**3-day Outlook**")
        prediction_cols[1].write(pick["prediction"])

        prediction_cols[2].write("**Signal Strength**")
        prediction_cols[2].write(f"{pick['confidence']}%")

        prediction_cols[3].write("**Current Simulated Value**")
        prediction_cols[3].write(f"${simulated_value:,.2f}")

        technical_cols = st.columns(7)
        technical_cols[0].metric("3 Day", f"{stock_data['three_day_trend']:.2f}%")
        technical_cols[1].metric("7 Day", f"{stock_data['seven_day_trend']:.2f}%")
        technical_cols[2].metric("20 Day MA Gap", f"{stock_data['ma_20_gap']:.2f}%")
        technical_cols[3].metric("50 Day MA Gap", f"{stock_data['ma_50_gap']:.2f}%")
        technical_cols[4].metric("Volume", f"{stock_data['volume_change']:.2f}%")
        technical_cols[5].metric("RSI", f"{stock_data['rsi']:.1f}")
        technical_cols[6].metric("Volatility", f"{stock_data['volatility']:.2f}%")

        fundamental_cols = st.columns(5)
        fundamental_cols[0].metric("Revenue Growth", f"{fundamental_data['revenue_growth'] * 100:.1f}%")
        fundamental_cols[1].metric("Earnings Growth", f"{fundamental_data['earnings_growth'] * 100:.1f}%")
        fundamental_cols[2].metric("Profit Margin", f"{fundamental_data['profit_margin'] * 100:.1f}%")
        fundamental_cols[3].metric("Forward P/E", f"{fundamental_data['forward_pe']:.1f}")
        fundamental_cols[4].metric("Analyst Upside", f"{fundamental_data['analyst_upside']:.1f}%")

        news_cols = st.columns(2)
        news_cols[0].metric("News Score", news_data["news_score"])
        news_cols[1].metric("Sector 7 Day Trend", f"{sector_data['seven_day_trend']:.2f}%")

        if news_data["headlines"]:
            with st.expander("Recent headlines used by the model"):
                for headline in news_data["headlines"]:
                    st.write(f"- {headline}")

        st.caption(
            f"Market: {stock_data['data_source']} | Fundamentals: {fundamental_data['data_source']} | News: {news_data['news_source']}"
        )

st.header("Candidate Comparison")

for sector_name, candidates in all_candidates_by_sector.items():
    with st.expander(f"{sector_name} candidates"):
        for candidate in sorted(candidates, key=lambda item: item["score"], reverse=True):
            st.write(
                f"{candidate['ticker']} - {candidate['company_name']}: "
                f"score {candidate['score']}, "
                f"{candidate['prediction']}, "
                f"confidence {candidate['confidence']}%"
            )

st.header("Saved Prediction Evaluation")
history_rows = load_prediction_history()

if history_rows:
    st.write("The app saves each daily pick and marks it correct or incorrect after the target date passes.")
    st.dataframe(
        history_rows,
        column_config={
            0: "Prediction Date",
            1: "Target Date",
            2: "Sector",
            3: "Ticker",
            4: "Company",
            5: "Selected Price",
            6: "Score",
            7: "Prediction",
            8: "Confidence",
            9: "Result",
            10: "Return",
        },
        hide_index=True,
    )
else:
    st.write("No saved prediction history yet.")

st.header("Daily Trend Predictions vs Reality")
daily_forecast_rows = load_daily_forecasts()

if daily_forecast_rows:
    st.write(
        "This rolling table keeps the latest 7 forecast dates for each sector. "
        "Future dates stay pending until market data exists."
    )
    st.dataframe(
        daily_forecast_rows,
        column_config={
            0: "Forecast Date",
            1: "Sector",
            2: "Ticker",
            3: "Company",
            4: "AI Predicted Direction",
            5: "Reality",
            6: "Result",
            7: "Actual Return",
            8: "Confidence",
        },
        hide_index=True,
    )
else:
    st.write("No daily forecasts have been saved yet.")

st.info(
    "Optional keys: add FMP_API_KEY for stronger news data and OPENAI_API_KEY for AI-written explanations. "
    "Without keys, the app still runs using Yahoo Finance data and rule-based explanations."
)
