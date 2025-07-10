import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from typing import Optional
from contextlib import contextmanager
from fastapi import Query
import traceback
from pydantic import BaseModel, EmailStr
from fastapi import Body
from fastapi import Response
from datetime import datetime
from fastapi import APIRouter, Body

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],  # явно указываем методы
    allow_headers=["*"],
)


class ArticleData(BaseModel):
    title: str

class ArticleSection(BaseModel):
    title: str
    content: str

class ArticleUpdate(BaseModel):
    article: ArticleData
    sections: List[ArticleSection]


class SectionContent(BaseModel):
    html_content: str

class Article(BaseModel):
    id: int
    title: str
    medical_section: str
    version: Optional[str]
    mkb: Optional[str]
    is_archived: bool
    updated_at: Optional[str]  # ← Обязательно нужно добавить!

class PaginatedArticles(BaseModel):
    items: List[Article]
    total: int
    page: int
    per_page: int


DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL не задан в .env")




from fastapi import APIRouter, HTTPException
from assistant.models import find_article_by_question


router = APIRouter()
from pydantic import BaseModel

class AskAIRequest(BaseModel):
    question: str

from assistant.chat import answer_user_question

@router.post("/ask-ai")
async def ask_ai(request: AskAIRequest):
    print(f"Получен запрос: {request.question}")
    try:
        print("Начинаем обработку запроса...")
        answer = answer_user_question(request.question, app.state.db_conn)
        print(f"Получен ответ: {answer[:100]}...")
        return {"answer": answer}
    except Exception as e:
        print(f"Ошибка в ask_ai endpoint: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

app.include_router(router)


@app.on_event("startup")
def startup_db():
    app.state.db_conn = psycopg2.connect(
        dsn=DATABASE_URL,
        cursor_factory=RealDictCursor
    )
    print("✅ Подключение к БД установлено")

@app.on_event("shutdown")
def shutdown_db():
    app.state.db_conn.close()
    print("⛔ Подключение к БД закрыто")

@app.get("/ping")
def ping():
    return {"status": "ok"}



@contextmanager
def get_cursor():
    conn = psycopg2.connect(
        dsn=DATABASE_URL,
        cursor_factory=RealDictCursor
    )
    try:
        cursor = conn.cursor()
        yield cursor
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()


@app.get("/routes-debug")
def list_routes():
    return [{"path": route.path, "name": route.name} for route in app.router.routes]


@app.get("/articles/versions")
def get_versions():
    try:
        with get_cursor() as cur:
            query = """
                SELECT DISTINCT version 
                FROM articles 
                WHERE version IS NOT NULL AND version != '' 
                ORDER BY version
            """
            cur.execute(query)
            versions = [row['version'] for row in cur.fetchall()]
            return versions

    except Exception as e:
        print("❌ Ошибка:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/articles", response_model=PaginatedArticles)
def get_articles(
    search: Optional[str] = None,
    section_ids: Optional[str] = None,
    versions: Optional[str] = None,
    is_archived: Optional[bool] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100)
):
    try:
        with get_cursor() as cur:
            filters = []
            params = []

            if section_ids:
                id_list = [int(id) for id in section_ids.split(',')]
                filters.append("ms.id = ANY(%s)")
                params.append(id_list)

            if versions:
                versions_list = [v.strip() for v in versions.split(',') if v.strip()]
                filters.append("a.version IN %s")
                params.append(tuple(versions_list))

            if search:
                filters.append("(a.title ILIKE %s OR a.mkb ILIKE %s)")
                params.extend([f"%{search}%"] * 2)

            if is_archived is not None:
                filters.append("a.is_archived = %s")
                params.append(is_archived)

            where_clause = " AND ".join(filters)
            where_sql = f"WHERE {where_clause}" if where_clause else ""

            # Считаем общее количество
            count_sql = f"""
                SELECT COUNT(DISTINCT a.id)
                FROM articles a
                CROSS JOIN unnest(string_to_array(a.medical_section, ',')) AS section_name
                INNER JOIN medical_sections ms ON trim(ms.name) = trim(section_name)
                {where_sql}
            """
            cur.execute(count_sql, params)
            total = cur.fetchone()['count']

            offset = (page - 1) * per_page

            # Получаем сразу нужные статьи с фильтрацией и пагинацией
            data_query = f"""
                SELECT DISTINCT a.id, a.title, a.medical_section, a.version, a.mkb, a.is_archived, COALESCE(a.updated_at, a.created_at) AS updated_at
                FROM articles a
                CROSS JOIN unnest(string_to_array(a.medical_section, ',')) AS section_name
                INNER JOIN medical_sections ms ON trim(ms.name) = trim(section_name)
                {where_sql}
                ORDER BY a.id
                LIMIT %s OFFSET %s
            """
            cur.execute(data_query, params + [per_page, offset])
            items = cur.fetchall()

            for item in items:
                if item["updated_at"]:
                    item["updated_at"] = item["updated_at"].strftime("%d.%m.%Y %H:%M:%S")

            return {
                "items": items,
                "total": total,
                "page": page,
                "per_page": per_page
            }


    except Exception as e:
        print("❌ Ошибка:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/articles")
def create_article(data: dict = Body(...)):
    try:
        with get_cursor() as cur:
            title = data.get("title")
            version = data.get("version")
            medical_section = data.get("medical_section")
            mkb = data.get("mkb")
            is_archived = data.get("is_archived", False)

            if not title or not medical_section:
                raise HTTPException(status_code=400, detail="Отсутствует обязательное поле")

            cur.execute("""
                INSERT INTO articles (title, version, medical_section, mkb, is_archived, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                RETURNING id, title, version, medical_section, mkb, is_archived, updated_at
            """, (title, version, medical_section, mkb, is_archived))

            result = cur.fetchone()
            return dict(result)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/articles/{article_id}")
def get_article_content(article_id: int):
    try:
        cur = app.state.db_conn.cursor()
        cur.execute(
            """
            SELECT
                a.title,
                a.mkb,
                a.version,
                a.medical_section,
                a.is_archived,
                s.id AS section_id,
                s.html_content
            FROM articles a
            LEFT JOIN article_sections s ON a.id = s.article_id
            WHERE a.id = %s
            """,
            (article_id,)
        )
        contents = cur.fetchall()
        cur.close()

        if not contents:
            raise HTTPException(status_code=404, detail="Статья не найдена")

        return {
            "title": contents[0]["title"],
            "mkb": contents[0]["mkb"],
            "version": contents[0]["version"],
            "medical_section": contents[0]["medical_section"],
            "is_archived": contents[0]["is_archived"],
            "contents": [
                {
                    "section_id": row["section_id"],
                    "html_content": row["html_content"]
                }
                for row in contents if row["html_content"]
            ]
        }
    except Exception as e:
        print("❌ Ошибка:", e)
        raise HTTPException(status_code=500, detail=str(e))


class ArticleSection(BaseModel):
    id: int
    section_title: str
    html_content: str

class ArticleFullResponse(BaseModel):
    id: int
    title: str
    mkb: str
    version: str
    medical_section: str
    is_archived: Optional[bool] = None
    sections: List[ArticleSection]


@app.get("/articles/{article_id}/full", response_model=ArticleFullResponse)
def get_full_article(article_id: int):
    try:
        conn = app.state.db_conn
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                a.id,
                a.title,
                a.mkb,
                a.version,
                a.medical_section,
                a.is_archived,
                s.id AS section_id,
                s.section_title,
                s.html_content
            FROM articles a
            LEFT JOIN article_sections s ON a.id = s.article_id
            WHERE a.id = %s
            ORDER BY s.id ASC
            """,
            (article_id,)
        )
        rows = cur.fetchall()

        if not rows:
            raise HTTPException(status_code=404, detail="Статья не найдена")

        article = {
            "id": rows[0]["id"],
            "title": rows[0]["title"],
            "mkb": rows[0]["mkb"],
            "version": rows[0]["version"],
            "medical_section": rows[0]["medical_section"],
            "is_archived": rows[0]["is_archived"],
            "sections": [
                {
                    "id": row["section_id"],
                    "section_title": row["section_title"],
                    "html_content": row["html_content"]
                }
                for row in rows if row["section_id"] is not None
            ]
        }

        conn.commit()
        cur.close()
        return article

    except Exception as e:
        if cur:
            cur.close()
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))


class ArticleFullUpdate(BaseModel):
    title: str
    mkb: str
    version: str
    medical_section: str
    is_archived: Optional[bool] = None
    sections: List[ArticleSection]

@app.put("/articles/{article_id}/full")
def update_full_article(article_id: int, data: ArticleFullUpdate = Body(...)):
    try:
        cur = app.state.db_conn.cursor()

        # Проверяем существование статьи
        cur.execute(
            "SELECT id FROM articles WHERE id = %s",
            (article_id,)
        )
        if not cur.fetchone():
            cur.close()
            raise HTTPException(status_code=404, detail="Статья не найдена")

        # Обновляем основную информацию статьи
        cur.execute(
            """
            UPDATE articles
            SET title = %s, 
                mkb = %s, 
                version = %s, 
                medical_section = %s, 
                is_archived = %s
            WHERE id = %s
            """,
            (data.title, data.mkb, data.version, data.medical_section, data.is_archived, article_id)
        )

        # Обновляем секции
        if hasattr(data, 'sections'):
            # Удаляем старые секции
            cur.execute("DELETE FROM article_sections WHERE article_id = %s", (article_id,))

            # Добавляем новые секции
            for section in data.sections:
                cur.execute(
                    """
                    INSERT INTO article_sections (article_id, section_title, html_content)
                    VALUES (%s, %s, %s)
                    """,
                    (article_id, section.section_title, section.html_content)
                )

        app.state.db_conn.commit()
        cur.close()
        return {"status": "success", "article_id": article_id}
    except Exception as e:
        app.state.db_conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/logout")
def logout(response: Response):
    response.delete_cookie("refresh_token")
    return {"detail": "Logged out"}


@app.put("/articles/{article_id}/sections/{section_id}")
def update_section(article_id: int, section_id: int, data: dict = Body(...)):
    try:
        cur = app.state.db_conn.cursor()

        # Проверяем существование секции
        cur.execute(
            """
            SELECT id FROM article_sections
            WHERE article_id = %s AND id = %s
            """,
            (article_id, section_id)
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Секция не найдена")

        section_title = data.get('title') or data.get('section_title')
        html_content = data.get('html_content')

        if not section_title or not html_content:
            raise HTTPException(
                status_code=400,
                detail="Отсутствуют обязательные поля title/section_title или html_content"
            )

        # Обновляем секцию
        cur.execute(
            """
            UPDATE article_sections
            SET section_title = %s,
                html_content = %s
            WHERE article_id = %s AND id = %s
            RETURNING id, section_title, html_content
            """,
            (section_title, html_content, article_id, section_id)
        )
        result = cur.fetchone()

        # Обновляем updated_at у статьи, если он null, ставим created_at
        cur.execute(
            """
            UPDATE articles
            SET updated_at = COALESCE(NOW(), created_at)
            WHERE id = %s RETURNING updated_at
            """,
            (article_id,)
        )
        updated_at_obj = cur.fetchone()["updated_at"]
        updated_at_str = updated_at_obj.isoformat()  # делает строку с T и микросекундами

        app.state.db_conn.commit()

        return {
            "id": result["id"],
            "section_title": result["section_title"],
            "html_content": result["html_content"],
            "updated_at": updated_at_str
        }

    except Exception as e:
        app.state.db_conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cur:
            cur.close()


@app.post("/articles/{article_id}/sections")
def create_section(article_id: int, data: dict = Body(...)):
    cur = None
    try:
        print("Полученные данные:", data)
        cur = app.state.db_conn.cursor()

        section_title = data.get('title') or data.get('section_title')
        html_content = data.get('html_content', '')

        if not section_title:
            raise HTTPException(status_code=400, detail="Отсутствует title/section_title")

        cur.execute(
            """
            INSERT INTO article_sections (article_id, section_title, html_content)
            VALUES (%s, %s, %s)
            RETURNING id, section_title, html_content
            """,
            (article_id, section_title, html_content)
        )

        result = cur.fetchone()

        if not result:
            app.state.db_conn.rollback()
            raise HTTPException(status_code=500, detail="Ошибка вставки: пустой результат")

        app.state.db_conn.commit()

        return {
            "id": result["id"],
            "section_title": result["section_title"],
            "html_content": result["html_content"]
        }

    except Exception as e:
        if app.state.db_conn:
            app.state.db_conn.rollback()
        print(f"Ошибка при создании секции: {str(e)}")
        raise HTTPException(status_code=500, detail="Ошибка при создании секции")
    finally:
        if cur:
            cur.close()


class LoginRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    email: EmailStr
    phone: str
    password: str
    full_name: str

@app.post("/login")
def login(data: LoginRequest):
    conn = psycopg2.connect(dsn=DATABASE_URL, cursor_factory=RealDictCursor)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, email, full_name, role, is_active, password FROM users WHERE email = %s",
        (data.email,)
    )
    user = cur.fetchone()
    cur.close()
    conn.close()
    if not user or user["password"] != data.password:
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="Пользователь не активен")
    return {
        "id": user["id"],
        "email": user["email"],
        "full_name": user["full_name"],
        "role": user["role"]
    }

@app.post("/register")
def register(data: RegisterRequest):
    conn = psycopg2.connect(dsn=DATABASE_URL, cursor_factory=RealDictCursor)
    cur = conn.cursor()
    try:
        # Проверка уникальности email и телефона
        cur.execute("SELECT id FROM users WHERE email = %s OR phone = %s", (data.email, data.phone))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="Email или телефон уже зарегистрированы")

        # Вставка нового пользователя
        cur.execute(
            """
            INSERT INTO users (email, phone, password, full_name)
            VALUES (%s, %s, %s, %s)
            RETURNING id, email, full_name
            """,
            (data.email, data.phone, data.password, data.full_name)
        )
        user = cur.fetchone()
        conn.commit()
        return user
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@app.get("/sections")
def get_sections():
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT id, name
                FROM medical_sections
                ORDER BY name;
            """)
            return cur.fetchall()
    except Exception as e:
        print("❌ Ошибка:", e)
        raise HTTPException(status_code=500, detail=str(e))