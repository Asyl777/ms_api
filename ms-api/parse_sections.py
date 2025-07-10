import requests
from bs4 import BeautifulSoup, Tag
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv

load_dotenv()


def get_db_connection():
    return psycopg2.connect(
        dsn=os.getenv("DATABASE_URL"),
        cursor_factory=RealDictCursor
    )


def contains_partner_info(tag: Tag) -> bool:
    if tag.name == "p":
        strong = tag.find("strong")
        return strong and "ИНФОРМАЦИЯ ПАРТНЕРОВ" in strong.get_text(strip=True)
    return False


def clean_article_content(article: Tag) -> Tag:
    # Удаляем блоки ATTENTION и ATTACHMENTS
    for tag in article.find_all(attrs={"data-section-name": ["ATTENTION", "ATTACHMENTS"]}):
        tag.decompose()

    # Удаляем партнерский рекламный блок
    start_tag = None
    for tag in article.find_all("p"):
        if contains_partner_info(tag):
            start_tag = tag
            break

    if start_tag:
        current = start_tag
        while current:
            next_tag = current.find_next_sibling()
            current.decompose()
            if (isinstance(next_tag, Tag) and
                    next_tag.name == "div" and
                    "---------------------------------------------------------" in next_tag.get_text()):
                next_tag.decompose()
                break
            current = next_tag

    return article


def parse_and_save_article(article_id: int, url: str, cursor) -> None:
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, "html.parser")

        article = soup.find("article")
        if not article:
            print(f"❌ Статья {article_id}: не найден тег article")
            return

        # Очищаем контент
        article = clean_article_content(article)

        # Находим все разделы
        sections = article.find_all("section", class_="page-section")

        # Удаляем старые разделы
        cursor.execute(
            "DELETE FROM article_sections WHERE article_id = %s",
            (article_id,)
        )

        # Сохраняем новые разделы
        for section in sections:
            title = section.find("h2", class_="page-section__title")
            title_text = title.get_text(strip=True) if title else "Без названия"

            # Делаем все ссылки некликабельными
            for a_tag in section.find_all("a"):
                if a_tag.has_attr("href"):
                    del a_tag["href"]

            html_content = str(section)

            cursor.execute("""
                           INSERT INTO article_sections (article_id, section_title, html_content)
                           VALUES (%s, %s, %s)
                           """, (article_id, title_text, html_content))

        print(f"✅ Статья {article_id}: обработано {len(sections)} разделов")

    except Exception as e:
        print(f"❌ Ошибка при обработке статьи {article_id}: {str(e)}")
        raise


def main():
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Получаем статьи из базы
        cur.execute("SELECT id, url FROM articles WHERE url IS NOT NULL")
        articles = cur.fetchall()

        for article in articles:
            print(f"📄 Обработка статьи {article['id']}...")
            parse_and_save_article(article['id'], article['url'], cur)
            conn.commit()

        print("\n✅ Парсинг завершен успешно")

    except Exception as e:
        print(f"\n❌ Ошибка: {str(e)}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()