import openai
import os
from .models import find_article_by_question
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def answer_user_question(question: str, db_conn):
    print(f"Ищем статью для вопроса: {question}")

    try:
        article = find_article_by_question(question, db_conn)
        print(f"Найденная статья: {article}")

        if not article:
            return "К сожалению, не удалось найти подходящую статью по вашему вопросу."

        # Формируем ссылку на статью
        article_url = f"http://localhost:8000/articles/{article['id']}/full"

        # Получаем только релевантные разделы
        cursor = db_conn.cursor()
        cursor.execute("""
                       SELECT section_title, html_content
                       FROM article_sections
                       WHERE article_id = %s
                       ORDER BY id LIMIT 3
                       """, (article['id'],))

        sections = cursor.fetchall()
        cursor.close()

        if not sections:
            return f"Найдена статья '{article['title']}', но её содержимое недоступно.\nСсылка: {article_url}"

        # Формируем сокращенный контент
        article_content = f"Статья: {article['title']}\n\n"
        total_chars = 0
        MAX_CHARS = 3000

        for section in sections:
            from bs4 import BeautifulSoup
            clean_text = BeautifulSoup(section['html_content'], 'html.parser').get_text()

            if len(clean_text) > 1000:
                clean_text = clean_text[:1000] + "..."

            section_text = f"Раздел: {section['section_title']}\n{clean_text}\n\n"

            if total_chars + len(section_text) > MAX_CHARS:
                break

            article_content += section_text
            total_chars += len(section_text)

        prompt = f"""Ответь кратко на русском языке на основе статьи:

{article_content}

Вопрос: {question}

Ответ:"""

        print(f"Отправляем запрос к OpenAI (длина: {len(article_content)} символов)")

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=256,
            temperature=0.3,
            timeout=30
        )

        answer_text = response.choices[0].message.content

        # Добавляем ссылку к ответу
        return f"{answer_text}\n\n[Подробнее: {article['title']}]({article_url})"

    except Exception as e:
        print(f"Ошибка в answer_user_question: {e}")
        import traceback
        traceback.print_exc()
        return f"Произошла ошибка при обработке запроса: {str(e)}"