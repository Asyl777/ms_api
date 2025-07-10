import re


def find_article_by_question(question: str, db_conn):
    cursor = db_conn.cursor()

    # Медицинские термины имеют приоритет
    medical_terms = []
    stop_words = {"как", "что", "где", "когда", "почему", "зачем", "ответь", "на", "русском", "языке", "по", "вылечить"}

    # Очищаем от знаков препинания и разбиваем на слова
    clean_question = re.sub(r'[^\w\s]', ' ', question.lower())
    words = clean_question.split()

    for word in words:
        if word not in stop_words and len(word) > 2:  # исключаем короткие слова
            medical_terms.append(word)

    # Ищем по медицинским терминам
    for term in medical_terms:
        print(f"Поиск по медицинскому термину: '{term}'")

        cursor.execute("""
                       SELECT id, title
                       FROM articles
                       WHERE LOWER(title) LIKE %s
                          OR LOWER(mkb) LIKE %s LIMIT 1
                       """, (f"%{term}%", f"%{term}%"))

        row = cursor.fetchone()
        print(f"Результат поиска: {row}")

        if row:
            try:
                # Поддерживаем и RealDictRow и обычные кортежи
                if hasattr(row, 'get'):  # RealDictRow
                    article_id = row['id']
                    article_title = row['title']
                else:  # Обычный кортеж
                    article_id = row[0]
                    article_title = row[1]

                cursor.close()
                return {"id": article_id, "title": article_title}
            except (KeyError, IndexError):
                continue

    cursor.close()
    return None