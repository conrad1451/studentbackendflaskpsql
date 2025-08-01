import os
from flask import Flask, request, jsonify, make_response
import jwt
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import requests
from jose import jwk, jwt as jose_jwt # Using python-jose for JWKS handling
import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Load environment variables
load_dotenv()

app = Flask(__name__)

# --- Configuration from Environment Variables ---
APP_SECRET_KEY = os.environ.get('JWT_SECRET')
DESCOPE_PROJECT_ID = os.environ.get('DESCOPE_PROJECT_ID')
NEON_DATABASE_URL = os.environ.get('NEON_DATABASE_URL')
FRONTEND_URL = os.environ.get('FRONTEND_URL')

if not APP_SECRET_KEY:
    raise RuntimeError("JWT_SECRET environment variable not set.")
if not DESCOPE_PROJECT_ID:
    raise RuntimeError("DESCOPE_PROJECT_ID environment variable not set.")
if not NEON_DATABASE_URL:
    raise RuntimeError("NEON_DATABASE_URL environment variable not set.")
if not FRONTEND_URL:
    print("WARNING: FRONTEND_URL not set. CORS might not work correctly.")

# Descope JWKS URL
DESCOPE_JWKS_URL = f"https://api.descope.com/{DESCOPE_PROJECT_ID}/.well-known/jwks"

# Simple in-memory cache for JWKS
_cached_jwks = None
_jwks_last_fetched = None
JWKS_CACHE_DURATION_SECONDS = 3600 # Cache for 1 hour

def get_jwks():
    global _cached_jwks, _jwks_last_fetched
    if _cached_jwks and _jwks_last_fetched and \
       (datetime.now(timezone.utc) - _jwks_last_fetched).total_seconds() < JWKS_CACHE_DURATION_SECONDS:
        return _cached_jwks

    try:
        response = requests.get(DESCOPE_JWKS_URL)
        response.raise_for_status()
        _cached_jwks = response.json()
        _jwks_last_fetched = datetime.now(timezone.utc)
        return _cached_jwks
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Failed to fetch Descope JWKS: {e}")
        return None

# --- Database Initialization and Connection ---
def get_db_connection():
    """Establishes and returns a connection to the Neon database."""
    try:
        conn = psycopg2.connect(NEON_DATABASE_URL)
        return conn
    except Exception as e:
        app.logger.error(f"Database connection failed: {e}")
        raise

def init_db():
    """Initializes the database schema (creates users table if it doesn't exist)."""
    conn = None
    try:
        conn = get_db_connection()
        # Ensure auto-commit for creating database (if needed, but we assume a single DB)
        # conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT) # Not needed if table creation
        cursor = conn.cursor()

        # Create the 'users' table
        # descope_user_id will be the 'sub' claim from Descope JWT
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                descope_user_id VARCHAR(255) UNIQUE NOT NULL,
                username VARCHAR(255) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE,
                first_login_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                last_login_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        app.logger.info("Database initialized successfully: 'users' table ensured.")
    except Exception as e:
        app.logger.error(f"Error initializing database: {e}")
    finally:
        if conn:
            conn.close()