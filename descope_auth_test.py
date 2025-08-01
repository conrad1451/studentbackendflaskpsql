# app.py
# -------------------------------------------------------------------------------------------------------------------
# This file contains the complete Flask backend application, now updated to handle multiple
# allowed frontend origins for CORS. This is essential for supporting both local development
# and production environments.
# -------------------------------------------------------------------------------------------------------------------

from flask import Flask, request, jsonify, make_response
import os
import jwt
import psycopg2
from datetime import datetime, timedelta

# Corrected imports
from descope import DescopeClient
from descope.exceptions import DescopeException

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# --- Application Configuration ---
app = Flask(__name__)
# Get environment variables
NEON_DB_URL = os.environ.get('NEON_DB_URL')
# We now use a comma-separated list for allowed origins
ALLOWED_ORIGINS_STR = os.environ.get('ALLOWED_ORIGINS')
DESCOPE_PROJECT_ID = os.environ.get('DESCOPE_PROJECT_ID')
DESCOPE_ACCESS_KEY = os.environ.get('DESCOPE_ACCESS_KEY')
APP_SECRET_KEY = os.environ.get('APP_SECRET_KEY')

# Check if all required environment variables are set
if not all([NEON_DB_URL, ALLOWED_ORIGINS_STR, DESCOPE_PROJECT_ID, DESCOPE_ACCESS_KEY, APP_SECRET_KEY]):
    raise EnvironmentError("One or more required environment variables are missing. Please check your .env file.")

# Parse the comma-separated string into a list of allowed origins
ALLOWED_ORIGINS = [origin.strip() for origin in ALLOWED_ORIGINS_STR.split(',')]

# Initialize the Descope client
try:
    descope_client = DescopeClient(project_id=DESCOPE_PROJECT_ID, management_key=DESCOPE_ACCESS_KEY)
except DescopeException as e:
    print(f"Failed to initialize DescopeClient: {e}")
    descope_client = None

# --- Helper function to get the allowed origin for the current request ---
# This is crucial for handling multiple origins correctly in the headers.
def get_request_origin():
    """
    Returns the origin of the current request if it is in the list of ALLOWED_ORIGINS.
    Returns None otherwise.
    """
    request_origin = request.headers.get('Origin')
    if request_origin and request_origin in ALLOWED_ORIGINS:
        return request_origin
    return None

# --- Database Initialization ---
# This function creates the 'users' table if it doesn't already exist.
def init_db():
    conn = None
    try:
        conn = psycopg2.connect(NEON_DB_URL)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                descope_user_id VARCHAR(255) PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                name VARCHAR(255),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                last_login_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        print("Database initialized successfully.")
    except Exception as e:
        print(f"Error initializing database: {e}")
    finally:
        if conn:
            conn.close()

# --- CORS Preflight Handling (Updated for multiple origins) ---
# Essential for cross-origin requests from your frontend. This handles the OPTIONS requests.
@app.before_request
def handle_options_requests():
    if request.method == 'OPTIONS':
        allowed_origin = get_request_origin()
        if allowed_origin:
            response = make_response()
            response.headers.add('Access-Control-Allow-Origin', allowed_origin)
            response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization')
            response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            response.headers.add('Access-Control-Allow-Credentials', 'true') # Required for cookies
            return response
        else:
            # If the origin is not allowed, return a 403 Forbidden
            return "CORS origin not allowed.", 403

# --- User Registration / Login (handled by Descope SSO callback) ---
@app.route('/api/auth/descope-sso-callback', methods=['POST'])
def sso_callback():
    allowed_origin = get_request_origin()
    if not allowed_origin:
        return "CORS origin not allowed.", 403

    if not descope_client:
        return jsonify({"error": "Descope client not initialized."}), 500

    try:
        data = request.json
        descope_jwt = data.get('sessionToken')
        
        if not descope_jwt:
            return jsonify({"error": "No session token provided."}), 400

        # Validate the Descope JWT
        validated_token = descope_client.validate_jwt(descope_jwt)
        descope_user_id = validated_token['sub']
        user_email = validated_token['email']
        user_name = validated_token.get('name')

        conn = None
        try:
            conn = psycopg2.connect(NEON_DB_URL)
            cur = conn.cursor()

            cur.execute("SELECT descope_user_id FROM users WHERE descope_user_id = %s", (descope_user_id,))
            user = cur.fetchone()

            if user:
                cur.execute(
                    "UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE descope_user_id = %s",
                    (descope_user_id,)
                )
            else:
                cur.execute(
                    "INSERT INTO users (descope_user_id, email, name) VALUES (%s, %s, %s)",
                    (descope_user_id, user_email, user_name)
                )
            
            conn.commit()

        except Exception as db_error:
            conn.rollback()
            print(f"Database error: {db_error}")
            return jsonify({"error": "Database operation failed."}), 500
        finally:
            if conn:
                conn.close()

        session_payload = {
            'sub': descope_user_id,
            'email': user_email,
            'exp': datetime.utcnow() + timedelta(hours=24)
        }
        session_token = jwt.encode(session_payload, APP_SECRET_KEY, algorithm='HS256')
        
        response = jsonify({
            "message": "Login successful",
            "email": user_email,
            "name": user_name
        })

        response.set_cookie(
            'sessionToken',
            value=session_token,
            httponly=True,
            samesite='Lax',
            secure=True,
            max_age=timedelta(hours=24)
        )

        response.headers.add('Access-Control-Allow-Origin', allowed_origin)
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        
        return response, 200

    except DescopeException as e:
        print(f"Descope authentication error: {e}")
        return jsonify({"error": "Authentication failed", "details": str(e)}), 401
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return jsonify({"error": "An internal server error occurred."}), 500


# --- Protected Endpoint Example ---
@app.route('/api/user-data', methods=['GET'])
def get_user_data():
    allowed_origin = get_request_origin()
    if not allowed_origin:
        return "CORS origin not allowed.", 403

    try:
        session_token = request.cookies.get('sessionToken')
        
        if not session_token:
            return jsonify({"error": "Unauthorized"}), 401
        
        payload = jwt.decode(session_token, APP_SECRET_KEY, algorithms=['HS256'])
        user_email = payload.get('email')

        response = jsonify({"message": f"Hello, {user_email}! This is protected data."})

        response.headers.add('Access-Control-Allow-Origin', allowed_origin)
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        
        return response, 200

    except jwt.ExpiredSignatureError:
        response = jsonify({"error": "Session expired, please log in again."})
        response.headers.add('Access-Control-Allow-Origin', allowed_origin)
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response, 401
    except jwt.InvalidTokenError:
        response = jsonify({"error": "Invalid session token."})
        response.headers.add('Access-Control-Allow-Origin', allowed_origin)
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response, 401
    except Exception as e:
        print(f"Error accessing protected endpoint: {e}")
        response = jsonify({"error": "An internal server error occurred."})
        response.headers.add('Access-Control-Allow-Origin', allowed_origin)
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response, 500


# --- Logout Endpoint ---
@app.route('/api/logout', methods=['POST'])
def logout():
    allowed_origin = get_request_origin()
    if not allowed_origin:
        return "CORS origin not allowed.", 403

    response = jsonify({"message": "Successfully logged out."})
    
    response.delete_cookie('sessionToken', httponly=True, samesite='Lax', secure=True)

    response.headers.add('Access-Control-Allow-Origin', allowed_origin)
    response.headers.add('Access-Control-Allow-Credentials', 'true')

    return response, 200


# --- Health Check (good for Render) ---
@app.route('/health')
def health_check():
    return "OK", 200


# --- Main entry point for Flask app ---
if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
