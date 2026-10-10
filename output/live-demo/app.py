import os
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from flask import Flask, abort, redirect, render_template_string, request, session, url_for

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY') or secrets.token_hex(32)
DB_NAME = str(Path(__file__).with_name('todo.db'))


@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def valid_csrf_token():
    submitted = request.form.get('csrf_token', '')
    expected = session.get('csrf_token', '')
    return bool(submitted and expected and secrets.compare_digest(submitted, expected))


def init_db():
    with get_db_connection() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                completed BOOLEAN NOT NULL DEFAULT 0
            )
        '''
        )
        conn.commit()


init_db()


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Flask Todo Application</title>
    <style>
        :root {
            --primary: #4f46e5;
            --primary-hover: #4338ca;
            --bg: #f9fafb;
            --card-bg: #ffffff;
            --text: #1f2937;
            --text-light: #6b7280;
            --border: #e5e7eb;
            --danger: #ef4444;
            --danger-hover: #dc2626;
            --success: #10b981;
            --success-hover: #059669;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background-color: var(--bg);
            color: var(--text);
            margin: 0;
            padding: 40px 20px;
            display: flex;
            justify-content: center;
        }

        .container {
            width: 100%;
            max-width: 600px;
            background: var(--card-bg);
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        }

        h1 {
            margin-top: 0;
            font-size: 24px;
            font-weight: 700;
            text-align: center;
            color: var(--primary);
            margin-bottom: 24px;
        }

        form.add-form {
            display: flex;
            gap: 10px;
            margin-bottom: 24px;
        }

        input[type="text"] {
            flex: 1;
            padding: 12px 16px;
            border: 1px solid var(--border);
            border-radius: 8px;
            font-size: 16px;
            outline: none;
            transition: border-color 0.2s;
        }

        input[type="text"]:focus {
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
        }

        button {
            background-color: var(--primary);
            color: white;
            border: none;
            padding: 12px 20px;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: background-color 0.2s;
        }

        button:hover {
            background-color: var(--primary-hover);
        }

        .task-list {
            list-style: none;
            padding: 0;
            margin: 0;
        }

        .task-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 14px 16px;
            border-bottom: 1px solid var(--border);
            transition: background-color 0.2s;
        }

        .task-item:last-child {
            border-bottom: none;
        }

        .task-item:hover {
            background-color: #f8fafc;
        }

        .task-title {
            flex: 1;
            font-size: 16px;
            margin-right: 15px;
            word-break: break-word;
        }

        .task-title.completed {
            text-decoration: line-through;
            color: var(--text-light);
        }

        .actions {
            display: flex;
            gap: 8px;
        }

        .btn-sm {
            padding: 6px 12px;
            font-size: 14px;
            border-radius: 6px;
        }

        .btn-complete {
            background-color: var(--success);
        }
        .btn-complete:hover {
            background-color: var(--success-hover);
        }

        .btn-undo {
            background-color: #f59e0b;
        }
        .btn-undo:hover {
            background-color: #d97706;
        }

        .btn-delete {
            background-color: var(--danger);
        }
        .btn-delete:hover {
            background-color: var(--danger-hover);
        }

        .empty-state {
            text-align: center;
            color: var(--text-light);
            padding: 30px 0;
            font-style: italic;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Flask Todo App</h1>
        
        <form class="add-form" action="{{ url_for('add_task') }}" method="POST">
            <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
            <input type="text" name="title" placeholder="What needs to be done?" required autocomplete="off">
            <button type="submit">Add Task</button>
        </form>

        <ul class="task-list">
            {% if tasks %}
                {% for task in tasks %}
                <li class="task-item">
                    <span class="task-title {% if task.completed %}completed{% endif %}">
                        {{ task.title }}
                    </span>
                    <div class="actions">
                        {% if task.completed %}
                            <form action="{{ url_for('toggle_task', id=task.id) }}" method="POST" style="display:inline;">
                                <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
                                <button type="submit" class="btn-sm btn-undo">Undo</button>
                            </form>
                        {% else %}
                            <form action="{{ url_for('toggle_task', id=task.id) }}" method="POST" style="display:inline;">
                                <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
                                <button type="submit" class="btn-sm btn-complete">Complete</button>
                            </form>
                        {% endif %}
                        <form action="{{ url_for('delete_task', id=task.id) }}" method="POST" style="display:inline;">
                            <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
                            <button type="submit" class="btn-sm btn-delete">Delete</button>
                        </form>
                    </div>
                </li>
                {% endfor %}
            {% else %}
                <div class="empty-state">No tasks yet. Add one above!</div>
            {% endif %}
        </ul>
    </div>
</body>
</html>
"""


@app.route('/')
def index():
    csrf_token = session.setdefault('csrf_token', secrets.token_urlsafe(32))
    with get_db_connection() as conn:
        tasks = conn.execute(
            'SELECT * FROM tasks ORDER BY id DESC'
        ).fetchall()
    return render_template_string(HTML_TEMPLATE, tasks=tasks, csrf_token=csrf_token)


@app.route('/add', methods=['POST'])
def add_task():
    if not valid_csrf_token():
        abort(400)
    title = request.form.get('title')
    if title and title.strip():
        with get_db_connection() as conn:
            conn.execute('INSERT INTO tasks (title, completed) VALUES (?, ?)', (title.strip(), 0))
            conn.commit()
    return redirect(url_for('index'))


@app.route('/toggle/<int:id>', methods=['POST'])
def toggle_task(id):
    if not valid_csrf_token():
        abort(400)
    with get_db_connection() as conn:
        task = conn.execute('SELECT completed FROM tasks WHERE id = ?', (id,)).fetchone()
        if task:
            new_status = 0 if task['completed'] else 1
            conn.execute('UPDATE tasks SET completed = ? WHERE id = ?', (new_status, id))
            conn.commit()
    return redirect(url_for('index'))


@app.route('/delete/<int:id>', methods=['POST'])
def delete_task(id):
    if not valid_csrf_token():
        abort(400)
    with get_db_connection() as conn:
        conn.execute('DELETE FROM tasks WHERE id = ?', (id,))
        conn.commit()
    return redirect(url_for('index'))


if __name__ == '__main__':
    init_db()
    app.run(debug=False, port=5000)