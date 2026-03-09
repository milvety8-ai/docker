import json
import os
from flask import Flask, jsonify, request
import psycopg2
from psycopg2.extras import RealDictCursor
import redis

app = Flask(__name__)

REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
CACHE_KEY = "tasks:list"
CACHE_TTL = 30

_redis = None


def get_redis():
    global _redis
    if _redis is None:
        _redis = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)
    return _redis


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


# Инициализация БД при запуске (gunicorn не выполняет if __name__ == "__main__")
init_db()


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


def _invalidate_cache():
    try:
        get_redis().delete(CACHE_KEY)
    except redis.RedisError:
        pass


@app.route("/api/tasks", methods=["GET"])
def get_tasks():
    try:
        cached = get_redis().get(CACHE_KEY)
        if cached:
            return jsonify(json.loads(cached))
    except redis.RedisError:
        pass

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM tasks ORDER BY created_at DESC")
    tasks = [dict(row) for row in cur.fetchall()]
    cur.close()
    conn.close()

    try:
        get_redis().setex(CACHE_KEY, CACHE_TTL, json.dumps(tasks, default=str))
    except redis.RedisError:
        pass

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
    _invalidate_cache()
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
    _invalidate_cache()
    return jsonify(task)


@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
    conn.commit()
    cur.close()
    conn.close()
    _invalidate_cache()
    return "", 204


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
