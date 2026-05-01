# Deployment Guide

This guide turns the Streamlit app into a website you can share.

## Best setup

Use:

- GitHub to store the project code
- Streamlit Community Cloud to host the website
- Supabase to store prediction history online

SQLite is fine on your computer, but Supabase is better for the hosted version because it keeps the prediction history online.

## Step 1: Create a Supabase project

1. Go to Supabase and create a new project.
2. Open the SQL Editor.
3. Copy everything from `supabase_schema.sql`.
4. Paste it into the SQL Editor and run it.
5. Go to Project Settings, then API.
6. Copy your project URL.
7. Copy your anon public key.

## Step 2: Put the project on GitHub

1. Create a new GitHub repository.
2. Upload these project files.
3. Do not upload `.streamlit/secrets.toml`.
4. It is okay to upload `.streamlit/secrets.example.toml`.

## Step 3: Deploy with Streamlit Community Cloud

1. Go to `https://share.streamlit.io`.
2. Sign in with GitHub.
3. Click Create app.
4. Choose your GitHub repository.
5. Set the main file path to `app.py`.
6. Open Advanced settings.
7. Paste your secrets.
8. Click Deploy.

## Step 4: Add secrets

Use this format in Streamlit Cloud secrets:

```toml
SUPABASE_URL = "your-supabase-project-url"
SUPABASE_KEY = "your-supabase-anon-key"
FMP_API_KEY = "optional-financial-modeling-prep-key"
OPENAI_API_KEY = "optional-openai-key"
```

Only `SUPABASE_URL` and `SUPABASE_KEY` are needed for online database history.

## Step 5: Check the website

When the site opens, look near the top for:

```text
Database mode: supabase
```

If it says:

```text
Database mode: sqlite
```

then the Supabase secrets are missing or spelled incorrectly.
