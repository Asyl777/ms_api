import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    dsn="postgresql://postgres:stom123@localhost:5432/articles_db",
    cursor_factory=RealDictCursor
)
cur = conn.cursor()
cur.execute("SELECT id, title, description FROM articles LIMIT 5;")
rows = cur.fetchall()
print(rows)
