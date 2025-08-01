# CHQ: Gemini AI generated this file
# app.py
# -------------------------------------------------------------------------------------------------------------------
# This file contains the complete Flask backend application for handling Descope authentication,
# session management with HTTP-only cookies, and database interaction with a Neon PostgreSQL database.
# -------------------------------------------------------------------------------------------------------------------

from flask import Flask, request, jsonify, make_response
from descope import DescopeClient, DescopeException
import os
import jwt
import psycopg2
from datetime import datetime, timedelta

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# --- Application Configuration ---
app = Flask(__name__)
# Get environment variables
NEON_DB_URL = os.environ.get('NEON_DB_URL')
FRONTEND_URL = os.environ.get('FRONTEND_URL')
DESCOPE_PROJECT_ID = os.environ.get('DESCOPE_PROJECT_ID')
DESCOPE_ACCESS_KEY = os.environ.get('DESCOPE_ACCESS_KEY')
APP_SECRET_KEY = os.environ.get('APP_SECRET_KEY')

# Check if all required environment variables are set
if not all([NEON_DB_URL, FRONTEND_URL, DESCOPE_PROJECT_ID, DESCOPE_ACCESS_KEY, APP_SECRET_KEY]):
    raise EnvironmentError("One or more required environment variables are missing. Please check your .env file.")

# Initialize the Descope client
try:
    descope_client = DescopeClient(project_id=DESCOPE_PROJECT_ID, management_key=DESCOPE_ACCESS_KEY)
except DescopeException as e:
    print(f"Failed to initialize DescopeClient: {e}")
    descope_client = None


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


# --- CORS Preflight Handling ---
# Essential for cross-origin requests from your frontend. This handles the OPTIONS requests.
@app.before_request
def handle_options_requests():
    if request.method == 'OPTIONS':
        if FRONTEND_URL:
            response = make_response()
            response.headers.add('Access-Control-Allow-Origin', FRONTEND_URL)
            response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization')
            response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            response.headers.add('Access-Control-Allow-Credentials', 'true') # Required for cookies
            return response
        else:
            return "CORS configuration missing.", 500


# --- User Registration / Login (handled by Descope SSO callback) ---
@app.route('/api/auth/descope-sso-callback', methods=['POST'])
def sso_callback():
    """
    This endpoint is called by the frontend after a successful Descope SSO login.
    It receives the Descope JWT, validates it, and then creates or updates a user
    in the PostgreSQL database. It then issues and sets an application-specific
    HTTP-only session cookie for the user.
    """
    if not descope_client:
        return jsonify({"error": "Descope client not initialized."}), 500

    try:
        data = request.json
        descope_jwt = data.get('sessionToken')
        
        if not descope_jwt:
            return jsonify({"error": "No session token provided."}), 400

        # Validate the Descope JWT
        # The SDK will verify the token's signature, expiry, and audience.
        validated_token = descope_client.validate_jwt(descope_jwt)
        descope_user_id = validated_token['sub']
        user_email = validated_token['email']
        user_name = validated_token.get('name')

        conn = None
        try:
            # Connect to the database
            conn = psycopg2.connect(NEON_DB_URL)
            cur = conn.cursor()

            # Check if user already exists
            cur.execute("SELECT descope_user_id FROM users WHERE descope_user_id = %s", (descope_user_id,))
            user = cur.fetchone()

            if user:
                # Update last login time for existing user
                cur.execute(
                    "UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE descope_user_id = %s",
                    (descope_user_id,)
                )
            else:
                # Create a new user
                cur.execute(
                    "INSERT INTO users (descope_user_id, email, name) VALUES (%s, %s, %s)",
                    (descope_user_id, user_email, user_name)
                )
            
            conn.commit()

        except Exception as db_error:
            conn.rollback() # Rollback in case of error
            print(f"Database error: {db_error}")
            return jsonify({"error": "Database operation failed."}), 500
        finally:
            if conn:
                conn.close()

        # --- Create and set a secure, HTTP-only session cookie ---
        # Generate your own application-specific JWT
        # This JWT will contain minimal, trusted user data and will be used for your session.
        session_payload = {
            'sub': descope_user_id,
            'email': user_email,
            'exp': datetime.utcnow() + timedelta(hours=24) # Session expires in 24 hours
        }
        session_token = jwt.encode(session_payload, APP_SECRET_KEY, algorithm='HS256')
        
        # Create a Flask response object
        response = jsonify({
            "message": "Login successful",
            "email": user_email,
            "name": user_name
        })

        # Set the session token as an HTTP-only cookie
        # This is the most secure way to handle session tokens.
        response.set_cookie(
            'sessionToken',
            value=session_token,
            httponly=True,
            samesite='Lax', # Protects against some CSRF attacks
            secure=True, # Requires HTTPS
            max_age=timedelta(hours=24) # Matches token expiry
        )

        # Allow CORS
        response.headers.add('Access-Control-Allow-Origin', FRONTEND_URL)
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
    """
    An example of a protected endpoint that requires a valid session cookie.
    It retrieves the session token from the cookie, verifies it, and
    returns a user-specific greeting.
    """
    try:
        # Get the session token from the cookies
        session_token = request.cookies.get('sessionToken')
        
        if not session_token:
            return jsonify({"error": "Unauthorized"}), 401
        
        # Decode and verify the session token using your secret key
        payload = jwt.decode(session_token, APP_SECRET_KEY, algorithms=['HS256'])
        user_email = payload.get('email')

        # Create a response with user-specific data
        response = jsonify({"message": f"Hello, {user_email}! This is protected data."})

        # Add CORS headers for the response
        response.headers.add('Access-Control-Allow-Origin', FRONTEND_URL)
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        
        return response, 200

    except jwt.ExpiredSignatureError:
        response = jsonify({"error": "Session expired, please log in again."})
        response.headers.add('Access-Control-Allow-Origin', FRONTEND_URL)
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response, 401
    except jwt.InvalidTokenError:
        response = jsonify({"error": "Invalid session token."})
        response.headers.add('Access-Control-Allow-Origin', FRONTEND_URL)
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response, 401
    except Exception as e:
        print(f"Error accessing protected endpoint: {e}")
        response = jsonify({"error": "An internal server error occurred."})
        response.headers.add('Access-Control-Allow-Origin', FRONTEND_URL)
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response, 500


# --- Logout Endpoint ---
@app.route('/api/logout', methods=['POST'])
def logout():
    """
    Logs out the user by deleting the session cookie.
    """
    response = jsonify({"message": "Successfully logged out."})
    
    # Delete the HTTP-only session cookie
    response.delete_cookie('sessionToken', httponly=True, samesite='Lax', secure=True)

    # Add CORS headers for the response
    response.headers.add('Access-Control-Allow-Origin', FRONTEND_URL)
    response.headers.add('Access-Control-Allow-Credentials', 'true')

    return response, 200


# --- Health Check (good for Render) ---
@app.route('/health')
def health_check():
    """
    Simple health check endpoint for monitoring purposes.
    """
    return "OK", 200


# --- Main entry point for Flask app ---
if __name__ == '__main__':
    # Initialize the database when the app starts
    init_db()
    # Run the Flask app
    app.run(host='0.0.0.0', port=5000, debug=True)
