import hmac
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import mysql.connector
from flask import Flask, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)

API_KEY = os.environ.get("API_KEY", "")
if not API_KEY:
    raise RuntimeError("API_KEY is required. Set it in .env / the container environment.")

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "requests.sqlite3"


def local_database_connection():
    return sqlite3.connect(DB_PATH, timeout=10)


def mysql_connection():
    return mysql.connector.connect(
        host=os.environ.get("MYSQL_HOST", "flask-mysql"),
        user=os.environ.get("MYSQL_USER"),
        password=os.environ.get("MYSQL_PASSWORD"),
        database=os.environ.get("MYSQL_DATABASE"),
    )


def initialize_users_table():
    conn = mysql_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            surname VARCHAR(100) NOT NULL,
            password VARCHAR(255) NOT NULL
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()


def initialize_database():
    with local_database_connection() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS counters (name TEXT PRIMARY KEY, value INTEGER NOT NULL)"
        )
        conn.execute("INSERT OR IGNORE INTO counters (name, value) VALUES ('requests', 0)")


def increment_request_count():
    with local_database_connection() as conn:
        conn.execute("UPDATE counters SET value = value + 1 WHERE name = 'requests'")


def get_request_count():
    with local_database_connection() as conn:
        row = conn.execute("SELECT value FROM counters WHERE name = 'requests'").fetchone()
    return row[0]


@app.route("/api/hello", methods=["GET"])
def hello():
    if not hmac.compare_digest(request.headers.get("X-API-Key", ""), API_KEY):
        return jsonify(error="Unauthorized: missing or invalid X-API-Key"), 401
    increment_request_count()
    name = request.args.get("name", "student")
    return jsonify(message=f"Hello, {name}!", lesson="Docker + Flask")


@app.route("/api/stats", methods=["GET"])
def stats():
    if not hmac.compare_digest(request.headers.get("X-API-Key", ""), API_KEY):
        return jsonify(error="Unauthorized: missing or invalid X-API-Key"), 401
    increment_request_count()
    return jsonify(authenticated_requests=get_request_count(), storage=str(DB_PATH))


@app.route("/api/echo", methods=["POST"])
def echo():
    if not hmac.compare_digest(request.headers.get("X-API-Key", ""), API_KEY):
        return jsonify(error="Unauthorized: missing or invalid X-API-Key"), 401
    increment_request_count()
    if not request.is_json:
        return jsonify(error="Send a JSON body with Content-Type: application/json"), 415
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("message"), str):
        return jsonify(error="JSON must be an object containing a string 'message'"), 400
    return jsonify(echo=data["message"], received_at=datetime.now(timezone.utc).isoformat())


@app.route("/api/users", methods=["POST"])
def create_user():
    if not hmac.compare_digest(request.headers.get("X-API-Key", ""), API_KEY):
        return jsonify(error="Unauthorized: missing or invalid X-API-Key"), 401
    if not request.is_json:
        return jsonify(error="Send a JSON body with Content-Type: application/json"), 415
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="JSON must be an object"), 400
    for field in ("name", "surname", "password"):
        if not isinstance(data.get(field), str) or not data[field]:
            return jsonify(error=f"'{field}' is required and must be a non-empty string"), 400
    hashed_password = generate_password_hash(data["password"])  # never store plain-text passwords
    conn = mysql_connection()
    cursor = conn.cursor()
    sql = "INSERT INTO users (name, surname, password) VALUES (%s, %s, %s)"
    values = (data["name"], data["surname"], hashed_password)
    cursor.execute(sql, values)
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify(message="User created successfully"), 201


# Endpoint 5: GET /api/users — search users by id, name, or surname
@app.route("/api/users", methods=["GET"])
def get_users():
    if not hmac.compare_digest(request.headers.get("X-API-Key", ""), API_KEY):
        return jsonify(error="Unauthorized: missing or invalid X-API-Key"), 401
    user_id = request.args.get("id")
    name = request.args.get("name")
    surname = request.args.get("surname")
    if not any([user_id, name, surname]):
        return jsonify(error="Provide at least one query param: id, name, or surname"), 400
    conditions = []
    params = []
    if user_id:
        conditions.append("id = %s")
        params.append(user_id)
    if name:
        conditions.append("name = %s")
        params.append(name)
    if surname:
        conditions.append("surname = %s")
        params.append(surname)
    query = "SELECT id, name, surname FROM users"
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    # "SELECT id, name, surname FROM users WHERE id = %s AND name = %s AND surname = %s"
    conn = mysql_connection()
    cursor = conn.cursor(dictionary=True)  # returns rows as dicts instead of tuples
    print(f"[DEBUG] Executing query: '{query}' with params: '{params}'")
    cursor.execute(query, params)
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(users=users)


initialize_database()
initialize_users_table()

if __name__ == "__main__":
    port = int(os.environ.get("APP_PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
