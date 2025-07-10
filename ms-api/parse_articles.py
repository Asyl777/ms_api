import os
import requests
from bs4 import BeautifulSoup
from psycopg2 import sql
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

base_url = "https://diseases.medelement.com"
search_url = "https://diseases.medelement.com/search/load_data"

params = {
    "searched_data": "diseases",
    "q": "",
    "mq": "",
    "tq": "",
    "diseases_filter_type": "list",
    "diseases_content_type": "4",
    "section_medicine": "",
    "category_mkb": "0",
    "parent_category_mkb": "0",
    "skip": 10
}

headers = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://diseases.medelement.com/"
}

inserted = 0

while True:
    print(f"Загружаем с skip={params['skip']}")
    res = requests.get(search_url, params=params, headers=headers)
    soup = BeautifulSoup(res.text, "html.parser")
    links = soup.select(".results-item__title-link")

    if not links:
        break

    for link in links:
        title = link.get_text(strip=True)
        href = link.get("href")
        full_url = base_url + href

        article = link.find_parent("article")

        # Парсинг МКБ
        mkb_element = article.select_one(".results-item__value.results__category-mkb")
        mkb = mkb_element.get_text(strip=True) if mkb_element else None

        # Парсинг раздела медицины
        medical_section = None
        for div in article.find_all('div', class_='results-item__value'):
            label = div.find('label')
            if label and 'Раздел медицины:' in label.text:
                medical_section = div.get_text(strip=True).replace('Раздел медицины:', '').strip()
                break

        # Парсинг версии
        version = None
        for div in article.find_all('div', class_='results-item__value'):
            label = div.find('label')
            if label and 'Версия:' in label.text:
                version = div.get_text(strip=True).replace('Версия:', '').strip()
                break

        # Определяем архивность
        is_archived = article.select_one('.results-item__value.results__archive') is not None

        try:
            cur.execute(
                sql.SQL("""
                        INSERT INTO articles (title, url, medical_section, version, mkb, is_archived)
                        VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (url) DO
                        UPDATE SET
                            title = EXCLUDED.title,
                            medical_section = EXCLUDED.medical_section,
                            version = EXCLUDED.version,
                            mkb = EXCLUDED.mkb,
                            is_archived = EXCLUDED.is_archived,
                            updated_at = CURRENT_TIMESTAMP
                        """),
                (title, full_url, medical_section, version, mkb, is_archived)
            )

            if cur.rowcount > 0:
                inserted += 1
                status = "Обновлено" if cur.statusmessage.startswith("UPDATE") else "Добавлено"
                print(f"{status}: {title}")

            conn.commit()

        except Exception as e:
            print(f"Ошибка при обработке {title}: {str(e)}")
            conn.rollback()

    params["skip"] += len(links)

print(f"\nУспешно загружено {inserted} статей")

cur.close()
conn.close()