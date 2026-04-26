from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, HttpUrl


APP_NAME = os.getenv("APP_NAME", "FirstTest Cinema")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "/data/app.db"))
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"


class MovieIn(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    original_title: str = Field(default="", max_length=180)
    year: int | None = Field(default=None, ge=1888, le=2100)
    description: str = Field(default="", max_length=4000)
    poster_url: str = Field(default="", max_length=1000)
    player_url: str = Field(default="", max_length=1000)
    source_url: str = Field(default="", max_length=1000)
    genre: str = Field(default="", max_length=120)


class ListUpdate(BaseModel):
    status: str = Field(pattern="^(planned|watching|watched|favorite|none)$")


class RatingUpdate(BaseModel):
    rating: int = Field(ge=1, le=10)


class NoteUpdate(BaseModel):
    note: str = Field(max_length=4000)


class CommentIn(BaseModel):
    author: str = Field(default="Я", max_length=80)
    content: str = Field(min_length=1, max_length=2000)


def dict_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


@contextmanager
def db() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def require_admin(x_admin_token: Annotated[str | None, Header()] = None) -> None:
    if ADMIN_TOKEN and x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Admin token is required")


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS movies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                original_title TEXT NOT NULL DEFAULT '',
                year INTEGER,
                description TEXT NOT NULL DEFAULT '',
                poster_url TEXT NOT NULL DEFAULT '',
                player_url TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL DEFAULT '',
                genre TEXT NOT NULL DEFAULT '',
                list_status TEXT NOT NULL DEFAULT 'none',
                rating INTEGER,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                movie_id INTEGER NOT NULL,
                author TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(movie_id) REFERENCES movies(id) ON DELETE CASCADE
            );

            CREATE TRIGGER IF NOT EXISTS movies_updated_at
            AFTER UPDATE ON movies
            FOR EACH ROW
            BEGIN
                UPDATE movies SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
            END;
            """
        )
        count = conn.execute("SELECT COUNT(*) AS total FROM movies").fetchone()["total"]
        if count == 0:
            seed_movies(conn)


def seed_movies(conn: sqlite3.Connection) -> None:
    examples = [
        (
            "Big Buck Bunny",
            2008,
            "Открытый короткометражный фильм Blender Foundation. Удобный легальный пример для проверки плеера.",
            "https://peach.blender.org/wp-content/uploads/title_anouncement.jpg",
            "https://www.youtube.com/embed/aqz-KE-bpKQ",
            "https://peach.blender.org/",
            "Animation",
        ),
        (
            "Sintel",
            2010,
            "Открытый анимационный фильм Blender Foundation, опубликованный как свободный проект.",
            "https://download.blender.org/durian/poster/sintel_poster.jpg",
            "https://www.youtube.com/embed/eRsGyueVLvQ",
            "https://durian.blender.org/",
            "Fantasy",
        ),
    ]
    conn.executemany(
        """
        INSERT INTO movies(title, year, description, poster_url, player_url, source_url, genre)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        examples,
    )


app = FastAPI(title=APP_NAME)
app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "app": APP_NAME}


@app.get("/api/movies")
def list_movies(query: str = "", status: str = "all") -> list[dict[str, Any]]:
    filters = []
    params: list[Any] = []
    if query:
        filters.append("(title LIKE ? OR original_title LIKE ? OR genre LIKE ?)")
        like = f"%{query}%"
        params.extend([like, like, like])
    if status != "all":
        filters.append("list_status = ?")
        params.append(status)

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    with db() as conn:
        rows = conn.execute(
            f"""
            SELECT id, title, original_title, year, description, poster_url, player_url,
                   source_url, genre, list_status, rating, note, created_at, updated_at
            FROM movies
            {where}
            ORDER BY updated_at DESC, id DESC
            """,
            params,
        ).fetchall()
        return [dict_from_row(row) for row in rows]


@app.post("/api/movies", dependencies=[Depends(require_admin)])
def create_movie(payload: MovieIn) -> dict[str, Any]:
    with db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO movies(title, original_title, year, description, poster_url, player_url, source_url, genre)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.title,
                payload.original_title,
                payload.year,
                payload.description,
                payload.poster_url,
                payload.player_url,
                payload.source_url,
                payload.genre,
            ),
        )
        movie_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM movies WHERE id = ?", (movie_id,)).fetchone()
        return dict_from_row(row)


@app.get("/api/movies/{movie_id}")
def get_movie(movie_id: int) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT * FROM movies WHERE id = ?", (movie_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Movie not found")
        movie = dict_from_row(row)
        comments = conn.execute(
            "SELECT id, author, content, created_at FROM comments WHERE movie_id = ? ORDER BY id DESC",
            (movie_id,),
        ).fetchall()
        movie["comments"] = [dict_from_row(comment) for comment in comments]
        return movie


@app.put("/api/movies/{movie_id}/list", dependencies=[Depends(require_admin)])
def update_list_status(movie_id: int, payload: ListUpdate) -> dict[str, Any]:
    with db() as conn:
        result = conn.execute(
            "UPDATE movies SET list_status = ? WHERE id = ?",
            (payload.status, movie_id),
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Movie not found")
        return {"ok": True, "status": payload.status}


@app.put("/api/movies/{movie_id}/rating", dependencies=[Depends(require_admin)])
def update_rating(movie_id: int, payload: RatingUpdate) -> dict[str, Any]:
    with db() as conn:
        result = conn.execute("UPDATE movies SET rating = ? WHERE id = ?", (payload.rating, movie_id))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Movie not found")
        return {"ok": True, "rating": payload.rating}


@app.put("/api/movies/{movie_id}/note", dependencies=[Depends(require_admin)])
def update_note(movie_id: int, payload: NoteUpdate) -> dict[str, Any]:
    with db() as conn:
        result = conn.execute("UPDATE movies SET note = ? WHERE id = ?", (payload.note, movie_id))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Movie not found")
        return {"ok": True}


@app.post("/api/movies/{movie_id}/comments", dependencies=[Depends(require_admin)])
def add_comment(movie_id: int, payload: CommentIn) -> dict[str, Any]:
    with db() as conn:
        exists = conn.execute("SELECT id FROM movies WHERE id = ?", (movie_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Movie not found")
        cursor = conn.execute(
            "INSERT INTO comments(movie_id, author, content) VALUES (?, ?, ?)",
            (movie_id, payload.author, payload.content),
        )
        row = conn.execute("SELECT * FROM comments WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict_from_row(row)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/{path:path}")
def spa_fallback(request: Request, path: str) -> FileResponse:
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(STATIC_DIR / "index.html")
