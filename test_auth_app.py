# CHQ: Gemini AI generated this file

from flask import Flask, request, jsonify, make_response
import jwt
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import os

# Load environment variables from a .env file
load_dotenv()

app = Flask(__name__)

# IMPORTANT: Use a strong, randomly generated secret key from an environment variable.
# DO NOT hardcode secrets in production.
# This key is used to sign your own session JWTs.
app.config['SECRET_KEY'] = os.environ.get('JWT_SECRET', 'a_super_secret_key_for_development')

# -----------------------------------------------------------
# Placeholder for Descope Token Verification
# In a real-world scenario, you would use Descope's SDK or public keys
# to securely verify the JWT that was sent from the frontend.
# This function simulates that process.
# -----------------------------------------------------------
def verify_descope_token(token):
    """Simulates verification of a Descope JWT."""
    print(f"Attempting to verify Descope token: {token}")
    # In production, you would:
    # 1. Fetch Descope's public keys
    # 2. Use a library like PyJWT to decode and verify the token's signature and claims
    # try:
    #     decoded_token = jwt.decode(token, descope_public_key, algorithms=["RS256"], audience="...Descope Audience...")
    #     return {"userId": decoded_token.get("sub")}
    # except jwt.InvalidTokenError:
    #     return None

    # For this example, we'll just check if the token exists and return a dummy user ID.
    if token:
        # Assuming the Descope token has a user ID in the 'sub' claim
        # We can extract it or just use a placeholder
        return {"userId": "descope-user-123"}
    return None

# -----------------------------------------------------------
# 1. Login Endpoint
# The frontend sends a POST request with the Descope JWT in the Authorization header.
# The backend verifies the token, generates its own session JWT, and sets
# it as an HTTP-only cookie.
# -----------------------------------------------------------
@app.route('/api/login-with-descope', methods=['POST'])
def login():
    # Extract the Descope token from the Authorization header
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'message': 'Descope token missing or malformed'}), 401
    
    descope_token = auth_header.split(' ')[1]

    # Verify the Descope token with our placeholder function
    user_info = verify_descope_token(descope_token)
    if not user_info:
        return jsonify({'message': 'Invalid or expired Descope token'}), 401

    # Generate our own, new session JWT for the backend
    payload = {
        'user_id': user_info['userId'],
        'exp': datetime.now(timezone.utc) + timedelta(hours=1) # Token expires in 1 hour
    }
    session_token = jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')

    # Create a response object
    response = make_response(jsonify({'message': 'Logged in successfully'}))

    # Set the HTTP-only cookie
    response.set_cookie(
        'sessionToken',
        session_token,
        httponly=True,  # Crucial: prevents client-side JS from accessing it
        secure=app.env == 'production', # Only send over HTTPS in production
        samesite='Lax', # Protects against CSRF
        max_age=3600    # Cookie lifetime in seconds (1 hour)
    )

    return response

# -----------------------------------------------------------
# 2. Protected Endpoint
# This endpoint requires an authenticated session. It automatically reads
# the HTTP-only cookie sent by the browser.
# -----------------------------------------------------------
@app.route('/api/protected-data', methods=['GET'])
def protected_data():
    # The browser automatically sends the 'sessionToken' cookie
    session_token = request.cookies.get('sessionToken')
    
    if not session_token:
        return jsonify({'message': 'Authentication required'}), 401

    try:
        # Decode and verify the session token using our secret key
        decoded_token = jwt.decode(session_token, app.config['SECRET_KEY'], algorithms=['HS256'])
        
        # The user is authenticated; you can now access their user ID
        user_id = decoded_token['user_id']
        
        return jsonify({
            'message': 'Welcome to the protected resource!',
            'user_id': user_id,
            'current_time': datetime.now(timezone.utc).isoformat()
        }), 200
    except jwt.ExpiredSignatureError:
        return jsonify({'message': 'Token has expired'}), 403
    except jwt.InvalidTokenError:
        return jsonify({'message': 'Invalid token'}), 403

# -----------------------------------------------------------
# 3. Logout Endpoint
# Clears the HTTP-only cookie, effectively logging the user out.
# -----------------------------------------------------------
@app.route('/api/logout', methods=['POST'])
def logout():
    response = make_response(jsonify({'message': 'Logged out successfully'}))
    response.delete_cookie('sessionToken')
    return response


# Basic route to check if the server is running
@app.route('/')
def home():
    return "This is for authenticating users before they can access data!"


if __name__ == '__main__':
    # For local development, you might set a .env file with JWT_SECRET
    # and run with `flask run`.
    # For production, use a more robust server like Gunicorn or uWSGI.
    app.run(debug=True, port=5000)