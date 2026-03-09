import os
from flask import Flask, jsonify, request
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)


def get_db():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "postgres"),
        database=os.environ.get("POSTGRES_DB", "taskdb"),
        user=os.environ.get("POSTGRES_USER", "appuser"),
        password=os.environ.get("POSTGRES_PASSWORD", "changeme"),
    )


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id SERIAL PRIMARY KEY,
            title VARCHAR(200) NOT NULL,
            done BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """
    )
    conn.commit()
    cur.close()
    conn.close()


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/tasks", methods=["GET"])
def get_tasks():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM tasks ORDER BY created_at DESC")
    tasks = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(tasks)


@app.route("/api/tasks", methods=["POST"])
def create_task():
    data = request.get_json()
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(
        "INSERT INTO tasks (title) VALUES (%s) RETURNING *",
        (data["title"],),
    )
    task = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return jsonify(task), 201


@app.route("/api/tasks/<int:task_id>", methods=["PATCH"])
def toggle_task(task_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(
        "UPDATE tasks SET done = NOT done WHERE id = %s RETURNING *",
        (task_id,),
    )
    task = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if task is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(task)


@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
    conn.commit()
    cur.close()
    conn.close()
    return "", 204


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
