#!/usr/bin/env python3
from assistant.vector_search import vector_search
from main import DATABASE_URL
import psycopg2
from psycopg2.extras import RealDictCursor

def main():
    print("🔄 Подключение к базе данных...")
    conn = psycopg2.connect(dsn=DATABASE_URL, cursor_factory=RealDictCursor)

    print("🔄 Индексация статей...")
    vector_search.index_articles(conn)
    print("✅ Индексация завершена")

    conn.close()

if __name__ == "__main__":
    main()