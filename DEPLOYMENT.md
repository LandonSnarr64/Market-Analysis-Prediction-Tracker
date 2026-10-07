# Deployment Guide

This guide explains how to deploy the Market Analysis & Prediction Tracker as a Streamlit web application.

## Recommended Setup

This project uses:

- GitHub for source code
- Streamlit Community Cloud for hosting
- Supabase for persistent prediction history

SQLite can be used when running the project locally. Supabase is recommended for a hosted deployment because the database persists independently of the Streamlit application.

## Step 1: Create a Supabase Project

1. Create a project in Supabase.
2. Open the SQL Editor.
3. Copy and run the database setup from `supabase_schema.sql`.
4. Enable Row Level Security (RLS) on the `predictions` and `daily_forecasts` tables.
5. Go to Project Settings → API Keys.
6. Copy the project URL.
7. Create or copy a Supabase secret API key for server-side database access.

The secret API key should only be used by the server-side Streamlit application. Never commit it to GitHub or expose it in client-side code.

## Step 2: Configure Secrets

For local development, create:

```text
.streamlit/secrets.toml
```

Add:

```toml
SUPABASE_URL = "your-supabase-project-url"
SUPABASE_KEY = "your-supabase-secret-key"

FMP_API_KEY = "optional-financial-modeling-prep-key"
OPENAI_API_KEY = "optional-openai-key"
```

`.streamlit/secrets.toml` is excluded from this repository through `.gitignore`.

Never place real API keys in `secrets.example.toml` or commit them to GitHub.

## Step 3: Deploy with Streamlit Community Cloud

1. Push the project to GitHub.
2. Open Streamlit Community Cloud.
3. Sign in with GitHub.
4. Create a new app.
5. Select this repository.
6. Set the main file path to `app.py`.
7. Open the app's secret/settings configuration.
8. Add the same Supabase URL and secret API key used above.
9. Deploy the application.

## Step 4: Verify the Connection

When the application starts, check the database status near the top of the page.

A successful Supabase connection displays:

```text
Database mode: supabase
```

If Supabase credentials are unavailable or the connection fails, the application falls back to:

```text
Database mode: sqlite
```

## Security

- Never commit `.streamlit/secrets.toml`, `.env`, or real API credentials.
- Keep Supabase Row Level Security enabled.
- Supabase secret keys are for trusted server-side environments only.
- Do not expose a Supabase secret key in browser-side JavaScript or other client-side code.
- Rotate or revoke a credential immediately if it is accidentally exposed.
