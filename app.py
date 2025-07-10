# CHQ: Gemini AI generated this

import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
from dotenv import load_dotenv
from urllib.parse import urlparse

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Configure CORS to allow requests from your React app
# IMPORTANT: In a production deployment, replace "http://localhost:3000"
# with the actual URL of your deployed React frontend.
CORS(app, resources={r"/api/*": {"origins": ["http://localhost:3000", "http://localhost:3500","http://localhost:5173","http://localhost:5174"]}})

# --- Database Connection ---
def get_db_connection():
    conn = None
    try:
        # Parse the DATABASE_URL from environment variables
        db_url = os.environ.get('DATABASE_URL')
        if not db_url:
            raise ValueError("DATABASE_URL environment variable is not set.")

        url = urlparse(db_url)
        conn = psycopg2.connect(
            host=url.hostname,
            database=url.path[1:],  # Remove leading slash from path
            user=url.username,
            password=url.password,
            port=url.port if url.port else 5432, # Default PostgreSQL port if not specified
            sslmode='require' # Neon requires SSL
        )
        print("Successfully connected to PostgreSQL database!") # For initial testing, you can leave this.
        return conn
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return None

# --- API Endpoints for Students ---

# GET all students
@app.route('/api/students', methods=['GET'])
def get_students():
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({"error": "Database connection failed"}), 500

        cur = conn.cursor()
        cur.execute('SELECT id, first_name, last_name, email, major, enrollment_date FROM students ORDER BY id ASC')
        students = cur.fetchall()
        cur.close()

        students_list = []
        for student in students:
            students_list.append({
                "id": student[0],
                "first_name": student[1],
                "last_name": student[2],
                "email": student[3],
                "major": student[4],
                "enrollment_date": student[5].isoformat() # Convert date object to ISO string
            })
        return jsonify(students_list)
    except Exception as e:
        print(f"Error fetching students: {e}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()

# GET a single student by ID
@app.route('/api/students/<int:student_id>', methods=['GET'])
def get_student(student_id):
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({"error": "Database connection failed"}), 500

        cur = conn.cursor()
        cur.execute('SELECT id, first_name, last_name, email, major, enrollment_date FROM students WHERE id = %s', (student_id,))
        student = cur.fetchone()
        cur.close()
        if student is None:
            return jsonify({"error": "Student not found"}), 404

        student_data = {
            "id": student[0],
            "first_name": student[1],
            "last_name": student[2],
            "email": student[3],
            "major": student[4],
            "enrollment_date": student[5].isoformat()
        }
        return jsonify(student_data)
    except Exception as e:
        print(f"Error fetching student: {e}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()

# POST a new student
@app.route('/api/students', methods=['POST'])
def add_student():
    data = request.get_json()
    first_name = data.get('first_name')
    last_name = data.get('last_name')
    email = data.get('email')
    major = data.get('major')

    if not all([first_name, last_name, email]):
        return jsonify({"error": "First name, last name, and email are required."}), 400

    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({"error": "Database connection failed"}), 500

        cur = conn.cursor()
        cur.execute(
            'INSERT INTO students (first_name, last_name, email, major) VALUES (%s, %s, %s, %s) RETURNING *',
            (first_name, last_name, email, major)
        )
        new_student = cur.fetchone()
        conn.commit() # Commit the transaction
        cur.close()

        new_student_data = {
            "id": new_student[0],
            "first_name": new_student[1],
            "last_name": new_student[2],
            "email": new_student[3],
            "major": new_student[4],
            "enrollment_date": new_student[5].isoformat()
        }
        return jsonify(new_student_data), 201
    except psycopg2.errors.UniqueViolation: # Catch unique constraint violation (e.g., duplicate email)
        conn.rollback() # Rollback on error
        return jsonify({"error": "Email already exists."}), 409
    except Exception as e:
        conn.rollback() # Rollback on error
        print(f"Error adding student: {e}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


# PUT (Update) a student
@app.route('/api/students/<int:student_id>', methods=['PUT'])
def update_student(student_id):
    data = request.get_json()
    first_name = data.get('first_name')
    last_name = data.get('last_name')
    email = data.get('email')
    major = data.get('major')

    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({"error": "Database connection failed"}), 500

        cur = conn.cursor()
        cur.execute(
            'UPDATE students SET first_name = %s, last_name = %s, email = %s, major = %s WHERE id = %s RETURNING *',
            (first_name, last_name, email, major, student_id)
        )
        updated_student = cur.fetchone()
        conn.commit()
        cur.close()

        if updated_student is None:
            return jsonify({"error": "Student not found"}), 404

        updated_student_data = {
            "id": updated_student[0],
            "first_name": updated_student[1],
            "last_name": updated_student[2],
            "email": updated_student[3],
            "major": updated_student[4],
            "enrollment_date": updated_student[5].isoformat()
        }
        return jsonify(updated_student_data)
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return jsonify({"error": "Email already exists for another student."}), 409
    except Exception as e:
        conn.rollback()
        print(f"Error updating student: {e}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()

# DELETE a student
@app.route('/api/students/<int:student_id>', methods=['DELETE'])
def delete_student(student_id):
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({"error": "Database connection failed"}), 500

        cur = conn.cursor()
        cur.execute('DELETE FROM students WHERE id = %s RETURNING *', (student_id,))
        deleted_student = cur.fetchone()
        conn.commit()
        cur.close()

        if deleted_student is None:
            return jsonify({"error": "Student not found"}), 404

        return jsonify({"message": "Student deleted successfully", "deleted_id": deleted_student[0]})
    except Exception as e:
        conn.rollback()
        print(f"Error deleting student: {e}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()

# Basic route to check if the server is running
@app.route('/')
def home():
    return "Flask Student API is running!"

if __name__ == '__main__':
    # Flask will automatically use the FLASK_APP and FLASK_ENV from .env
    # when run with 'flask run'. For direct execution, you can specify port.
    app.run(debug=os.environ.get('FLASK_ENV') == 'development', port=5000)