import os
import requests
from bs4 import BeautifulSoup
from psycopg2.extras import RealDictCursor
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL не задан в .env")

conn = psycopg2.connect(
    dsn=DATABASE_URL,
    cursor_factory=RealDictCursor
)
cur = conn.cursor()

try:
    cur.execute("ALTER TABLE medical_sections ADD CONSTRAINT unique_name UNIQUE (name);")
    conn.commit()
except:
    conn.rollback()

url = "https://diseases.medelement.com/?searched_data=diseases&q=&mq=&tq=&diseases_filter_type=section_medicine&diseases_content_type=4&section_medicine=&category_mkb=0&parent_category_mkb=0"
headers = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://diseases.medelement.com/"
}

try:
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    # Ищем все элементы с классом col-lg-9 col-md-9 col-sm-9 col-7 multilevel-list__item__body
    sections = soup.find_all("div", class_="col-lg-9 col-md-9 col-sm-9 col-7 multilevel-list__item__body")

    for section in sections:
        # Находим ссылку внутри секции
        link = section.select_one(".multilevel-list__item__title-link")
        if link:
            name = link.get_text(strip=True)

            if not name:
                continue

            try:
                cur.execute("""
                    INSERT INTO medical_sections (name)
                    VALUES (%s)
                    ON CONFLICT (name) DO NOTHING
                """, (name,))
                print(f"Добавлен раздел: {name}")
            except Exception as e:
                print(f"Ошибка при добавлении {name}: {e}")
                continue

    conn.commit()
    print("\nПарсинг завершен успешно")

except Exception as e:
    print(f"Ошибка: {e}")
    conn.rollback()

finally:
    cur.close()
    conn.close()