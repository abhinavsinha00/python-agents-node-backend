import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, g

app = Flask(__name__)
DATABASE = os.path.join(os.path.dirname(__file__), 'bookmarks.db')

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        db.execute('''
            CREATE TABLE IF NOT EXISTS bookmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT NOT NULL
            )
        ''')
        db.commit()

# Initialize DB on import so python -m flask --app app run works seamlessly
init_db()

@app.route('/')
def index():
    query = request.args.get('q', '').strip()
    db = get_db()
    if query:
        cur = db.execute(
            'SELECT * FROM bookmarks WHERE title LIKE ? ORDER BY id DESC',
            ('%' + query + '%',)
        )
    else:
        cur = db.execute('SELECT * FROM bookmarks ORDER BY id DESC')
    bookmarks = cur.fetchall()
    return render_template('index.html', bookmarks=bookmarks, query=query)

@app.route('/add', methods=['POST'])
def add_bookmark():
    title = request.form.get('title', '').strip()
    url = request.form.get('url', '').strip()
    if title and url:
        db = get_db()
        db.execute('INSERT INTO bookmarks (title, url) VALUES (?, ?)', (title, url))
        db.commit()
    return redirect(url_for('index'))

@app.route('/delete/<int:id>', methods=['POST'])
def delete_bookmark(id):
    db = get_db()
    db.execute('DELETE FROM bookmarks WHERE id = ?', (id,))
    db.commit()
    return redirect(url_for('index'))

# Create minimal templates and static files automatically if they don't exist
os.makedirs(os.path.join(os.path.dirname(__file__), 'templates'), exist_ok=True)
os.makedirs(os.path.join(os.path.dirname(__file__), 'static'), exist_ok=True)

INDEX_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mini Bookmark Manager</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
    <div class="container">
        <header>
            <h1>🔖 Bookmark Manager</h1>
            <p>Save and organize your favorite links</p>
        </header>

        <section class="card add-section">
            <h2>Add New Bookmark</h2>
            <form action="{{ url_for('add_bookmark') }}" method="POST">
                <div class="form-group">
                    <label for="title">Title</label>
                    <input type="text" id="title" name="title" placeholder="e.g. GitHub" required>
                </div>
                <div class="form-group">
                    <label for="url">URL</label>
                    <input type="url" id="url" name="url" placeholder="https://github.com" required>
                </div>
                <button type="submit" class="btn btn-primary">Add Bookmark</button>
            </form>
        </section>

        <section class="card search-section">
            <form action="{{ url_for('index') }}" method="GET" class="search-form">
                <input type="text" name="q" placeholder="Search by title..." value="{{ query }}">
                <button type="submit" class="btn btn-secondary">Search</button>
                {% if query %}
                    <a href="{{ url_for('index') }}" class="btn btn-outline">Clear</a>
                {% endif %}
            </form>
        </section>

        <section class="card list-section">
            <h2>Saved Bookmarks</h2>
            {% if bookmarks %}
                <ul class="bookmark-list">
                    {% for bm in bookmarks %}
                        <li>
                            <div class="bookmark-info">
                                <strong>{{ bm.title }}</strong>
                                <a href="{{ bm.url }}" target="_blank" rel="noopener noreferrer">{{ bm.url }}</a>
                            </div>
                            <form action="{{ url_for('delete_bookmark', id=bm.id) }}" method="POST" style="display:inline;">
                                <button type="submit" class="btn btn-danger">Delete</button>
                            </form>
                        </li>
                    {% endfor %}
                </ul>
            {% else %}
                <p class="empty-msg">No bookmarks found.</p>
            {% endif %}
        </section>
    </div>
</body>
</html>
'''

STYLE_CSS = '''* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background-color: #f4f7f6;
    color: #333;
    line-height: 1.6;
    padding: 2rem 1rem;
}

.container {
    max-width: 600px;
    margin: 0 auto;
}

header {
    text-align: center;
    margin-bottom: 2rem;
}

header h1 {
    color: #2c3e50;
    font-size: 2.2rem;
    margin-bottom: 0.3rem;
}

header p {
    color: #7f8c8d;
}

.card {
    background: #ffffff;
    padding: 1.5rem;
    border-radius: 8px;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
    margin-bottom: 1.5rem;
}

h2 {
    font-size: 1.2rem;
    color: #34495e;
    margin-bottom: 1rem;
    border-bottom: 2px solid #ecf0f1;
    padding-bottom: 0.5rem;
}

.form-group {
    margin-bottom: 1rem;
}

label {
    display: block;
    margin-bottom: 0.4rem;
    font-weight: 600;
    font-size: 0.9rem;
    color: #2c3e50;
}

input[type="text"],
input[type="url"] {
    width: 100%;
    padding: 0.7rem;
    border: 1px solid #ccd1d1;
    border-radius: 4px;
    font-size: 1rem;
    transition: border-color 0.2s;
}

input[type="text"]:focus,
input[type="url"]:focus {
    outline: none;
    border-color: #3498db;
}

.btn {
    padding: 0.6rem 1.2rem;
    border: none;
    border-radius: 4px;
    font-size: 0.95rem;
    font-weight: 600;
    cursor: pointer;
    text-decoration: none;
    display: inline-block;
    transition: background-color 0.2s;
}

.btn-primary {
    background-color: #3498db;
    color: white;
    width: 100%;
}

.btn-primary:hover {
    background-color: #2980b9;
}

.btn-secondary {
    background-color: #95a5a6;
    color: white;
}

.btn-secondary:hover {
    background-color: #7f8c8d;
}

.btn-outline {
    background-color: transparent;
    border: 1px solid #bdc3c7;
    color: #7f8c8d;
}

.btn-outline:hover {
    background-color: #ecf0f1;
}

.btn-danger {
    background-color: #e74c3c;
    color: white;
    padding: 0.4rem 0.8rem;
    font-size: 0.85rem;
}

.btn-danger:hover {
    background-color: #c0392b;
}

.search-form {
    display: flex;
    gap: 0.5rem;
}

.search-form input {
    flex: 1;
}

.bookmark-list {
    list-style: none;
}

.bookmark-list li {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.8rem 0;
    border-bottom: 1px solid #ecf0f1;
}

.bookmark-list li:last-child {
    border-bottom: none;
}

.bookmark-info {
    overflow: hidden;
    padding-right: 1rem;
}

.bookmark-info strong {
    display: block;
    color: #2c3e50;
    font-size: 1rem;
}

.bookmark-info a {
    color: #2980b9;
    font-size: 0.85rem;
    text-decoration: none;
    word-break: break-all;
}

.bookmark-info a:hover {
    text-decoration: underline;
}

.empty-msg {
    color: #95a5a6;
    text-align: center;
    font-style: italic;
    padding: 1rem 0;
}
'''

with open(os.path.join(os.path.dirname(__file__), 'templates', 'index.html'), 'w', encoding='utf-8') as f:
    f.write(INDEX_HTML)

with open(os.path.join(os.path.dirname(__file__), 'static', 'style.css'), 'w', encoding='utf-8') as f:
    f.write(STYLE_CSS)

if __name__ == '__main__':
    app.run(debug=True)
