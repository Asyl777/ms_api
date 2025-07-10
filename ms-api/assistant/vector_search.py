# import chromadb
# import openai
# import os
# from typing import List, Dict, Any
# from dotenv import load_dotenv
#
# # Загружаем переменные окружения
# load_dotenv()
#
# class VectorSearchEngine:
#     def __init__(self):
#         self.client = None
#         self.collection = None
#         self.openai_client = None
#         self._initialized = False
#
#     def initialize(self):
#         """Ленивая инициализация"""
#         if self._initialized:
#             return
#
#         # Отключаем телеметрию для избежания ошибок
#         os.environ["ANONYMIZED_TELEMETRY"] = "False"
#
#         # Проверяем наличие API ключа
#         api_key = os.getenv("OPENAI_API_KEY")
#         if not api_key:
#             print("❌ OPENAI_API_KEY не найден в переменных окружения")
#             return
#
#         # Новый API ChromaDB
#         self.client = chromadb.PersistentClient(path="./chroma_db")
#
#         # Получаем или создаем коллекцию
#         self.collection = self.client.get_or_create_collection(
#             name="medical_articles",
#             metadata={"hnsw:space": "cosine"}
#         )
#
#         self.openai_client = openai.OpenAI(api_key=api_key)
#         self._initialized = True
#         print("✅ Векторный поиск инициализирован")
#
#     def embed_text(self, text: str) -> List[float]:
#         """Создаем эмбеддинг через OpenAI"""
#         self.initialize()
#         response = self.openai_client.embeddings.create(
#             model="text-embedding-3-small",
#             input=text
#         )
#         return response.data[0].embedding
#
#     def index_articles(self, db_conn):
#         """Индексируем все статьи"""
#         self.initialize()
#         cursor = db_conn.cursor()
#
#         cursor.execute("""
#             SELECT a.id, a.title, a.mkb, a.medical_section,
#                    string_agg(s.section_title || ': ' || substring(
#                        regexp_replace(s.html_content, '<[^>]+>', '', 'g'), 1, 200
#                    ), ' | ') as content_summary
#             FROM articles a
#             LEFT JOIN article_sections s ON a.id = s.article_id
#             WHERE a.is_archived = false
#             GROUP BY a.id, a.title, a.mkb, a.medical_section
#             LIMIT 100
#         """)
#
#         articles = cursor.fetchall()
#         cursor.close()
#
#         if not articles:
#             print("❌ Нет статей для индексации")
#             return
#
#         # Подготавливаем данные для индексации
#         documents = []
#         metadatas = []
#         ids = []
#
#         for article in articles:
#             # Формируем текст для индексации
#             text = f"Заболевание: {article['title']}"
#             if article['mkb']:
#                 text += f" МКБ: {article['mkb']}"
#             if article['medical_section']:
#                 text += f" Раздел: {article['medical_section']}"
#             if article['content_summary']:
#                 text += f" Содержание: {article['content_summary']}"
#
#             documents.append(text)
#             metadatas.append({
#                 'id': article['id'],
#                 'title': article['title'],
#                 'mkb': article['mkb'],
#                 'medical_section': article['medical_section']
#             })
#             ids.append(str(article['id']))
#
#         # Очищаем старые данные
#         try:
#             self.collection.delete(where={})
#         except:
#             pass
#
#         # Добавляем в векторную базу
#         self.collection.add(
#             documents=documents,
#             metadatas=metadatas,
#             ids=ids
#         )
#
#         print(f"✅ Проиндексировано {len(documents)} статей")
#
#     def search_articles(self, question: str, top_k: int = 3) -> List[Dict[str, Any]]:
#         """Поиск релевантных статей"""
#         self.initialize()
#         try:
#             results = self.collection.query(
#                 query_texts=[question],
#                 n_results=top_k
#             )
#
#             articles = []
#             if results['metadatas'] and results['metadatas'][0]:
#                 for i, metadata in enumerate(results['metadatas'][0]):
#                     distance = results['distances'][0][i] if results['distances'] else 0
#                     relevance_score = 1.0 - distance
#
#                     articles.append({
#                         'id': metadata['id'],
#                         'title': metadata['title'],
#                         'mkb': metadata['mkb'],
#                         'medical_section': metadata['medical_section'],
#                         'relevance_score': relevance_score
#                     })
#
#             return articles
#
#         except Exception as e:
#             print(f"Ошибка поиска: {e}")
#             return []
#
# # Глобальный экземпляр (но НЕ инициализируем сразу)
# vector_search = VectorSearchEngine()