from __future__ import annotations

import os
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


APP_NAME = os.getenv("APP_NAME", "Личный кинотеатр")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "/data/app.db"))
KINOPOISK_API_KEY = os.getenv("KINOPOISK_API_KEY") or os.getenv("KINOPOISK_TECH_API_TOKEN", "")
KINOPOISK_API_BASE = "https://kinopoiskapiunofficial.tech"
KINOBD_API_URL = os.getenv("KINOBD_API_URL", "https://kinobd.net").rstrip("/")
KINOBD_TOKEN = os.getenv("KINOBD_TOKEN", "")
PLAYER_API_USER_AGENT = os.getenv(
    "PLAYER_API_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
)
KINOBD_PLAYER_PROVIDERS = ",".join(
    [
        "collaps",
        "vibix",
        "alloha",
        "kodik",
        "kinotochka",
        "flixcdn",
        "ashdi",
        "turbo",
        "videocdn",
        "bazon",
        "ustore",
        "pleer",
        "videospider",
        "iframe",
        "moonwalk",
        "hdvb",
        "cdnmovies",
        "lookbase",
        "kholobok",
        "videoapi",
        "voidboost",
        "trailer_local",
        "videoseed",
        "ia",
        "youtube",
        "ext",
        "trailer",
    ]
)
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"


class MovieIn(BaseModel):
    profile_id: int = Field(default=1, ge=1)
    kinopoisk_id: str = Field(default="", max_length=40)
    title: str = Field(min_length=1, max_length=180)
    original_title: str = Field(default="", max_length=180)
    year: int | None = Field(default=None, ge=1888, le=2100)
    description: str = Field(default="", max_length=4000)
    poster_url: str = Field(default="", max_length=1000)
    player_url: str = Field(default="", max_length=1000)
    source_url: str = Field(default="", max_length=1000)
    genre: str = Field(default="", max_length=120)
    list_status: str = Field(default="none", pattern="^(planned|watching|watched|favorite|none)$")


class ListUpdate(BaseModel):
    status: str = Field(pattern="^(planned|watching|watched|favorite|none)$")


class RatingUpdate(BaseModel):
    rating: int = Field(ge=1, le=10)


class NoteUpdate(BaseModel):
    note: str = Field(max_length=4000)


class PlayerUpdate(BaseModel):
    player_url: str = Field(default="", max_length=1000)


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    avatar: str = Field(default="🙂", min_length=1, max_length=20)


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
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                avatar TEXT NOT NULL DEFAULT '🙂',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS movies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER NOT NULL DEFAULT 1,
                kinopoisk_id TEXT NOT NULL DEFAULT '',
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
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
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

            CREATE TRIGGER IF NOT EXISTS profiles_updated_at
            AFTER UPDATE ON profiles
            FOR EACH ROW
            BEGIN
                UPDATE profiles SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
            END;
            """
        )
        profile_count = conn.execute("SELECT COUNT(*) AS count FROM profiles").fetchone()["count"]
        if profile_count == 0:
            conn.executemany(
                "INSERT INTO profiles(name, avatar) VALUES (?, ?)",
                [
                    ("Я", "🙂"),
                    ("Жена", "👩"),
                    ("Ребёнок", "👦"),
                ],
            )
        ensure_column(conn, "movies", "profile_id", "INTEGER NOT NULL DEFAULT 1")
        ensure_column(conn, "movies", "kinopoisk_id", "TEXT NOT NULL DEFAULT ''")
        conn.execute("UPDATE movies SET profile_id = 1 WHERE profile_id IS NULL OR profile_id < 1")
        conn.execute(
            """
            UPDATE movies
            SET kinopoisk_id = replace(replace(source_url, 'https://www.kinopoisk.ru/film/', ''), '/', '')
            WHERE kinopoisk_id = ''
              AND source_url LIKE 'https://www.kinopoisk.ru/film/%'
            """
        )
        # No demo rows: this is a personal library, so an empty list should stay empty.


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def kinopoisk_request(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    if not KINOPOISK_API_KEY:
        raise HTTPException(status_code=503, detail="KINOPOISK_API_KEY is not configured")

    query = urllib.parse.urlencode({key: value for key, value in (params or {}).items() if value})
    url = f"{KINOPOISK_API_BASE}{path}"
    if query:
        url = f"{url}?{query}"

    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "X-API-KEY": KINOPOISK_API_KEY,
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            import json

            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise HTTPException(status_code=exc.code, detail=detail or "Kinopoisk API error") from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail=f"Kinopoisk API is unavailable: {exc.reason}") from exc


def normalize_kinopoisk_search_item(item: dict[str, Any]) -> dict[str, Any]:
    kp_id = item.get("filmId") or item.get("kinopoiskId")
    title = item.get("nameRu") or item.get("nameEn") or item.get("nameOriginal") or "Без названия"
    return {
        "kp_id": str(kp_id or ""),
        "title": title,
        "original_title": item.get("nameEn") or item.get("nameOriginal") or "",
        "year": item.get("year"),
        "genre": ", ".join(genre.get("genre", "") for genre in item.get("genres", []) if genre.get("genre")),
        "poster_url": item.get("posterUrlPreview") or item.get("posterUrl") or "",
        "description": item.get("description") or "",
    }


def normalize_kinopoisk_film(payload: dict[str, Any]) -> dict[str, Any]:
    kp_id = payload.get("kinopoiskId") or payload.get("filmId")
    return {
        "kinopoisk_id": str(kp_id or ""),
        "title": payload.get("nameRu") or payload.get("nameEn") or payload.get("nameOriginal") or "Без названия",
        "original_title": payload.get("nameEn") or payload.get("nameOriginal") or "",
        "year": payload.get("year"),
        "description": payload.get("description") or payload.get("shortDescription") or "",
        "poster_url": payload.get("posterUrl") or payload.get("posterUrlPreview") or "",
        "player_url": "",
        "source_url": f"https://www.kinopoisk.ru/film/{kp_id}/" if kp_id else "",
        "genre": ", ".join(genre.get("genre", "") for genre in payload.get("genres", []) if genre.get("genre")),
    }


def external_json_request(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    query = urllib.parse.urlencode({key: value for key, value in (params or {}).items() if value})
    if query:
        url = f"{url}?{query}"

    request_headers = {"User-Agent": PLAYER_API_USER_AGENT, **(headers or {})}
    request = urllib.request.Request(url, headers=request_headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            import json

            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise HTTPException(status_code=exc.code, detail=detail or "External API error") from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail=f"External API is unavailable: {exc.reason}") from exc


def external_form_request(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    query = urllib.parse.urlencode({key: value for key, value in (params or {}).items() if value})
    if query:
        url = f"{url}?{query}"

    body = urllib.parse.urlencode({key: value for key, value in (data or {}).items() if value is not None}).encode()
    request_headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": PLAYER_API_USER_AGENT,
        **(headers or {}),
    }
    request = urllib.request.Request(url, data=body, headers=request_headers, method="POST")

    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            import json

            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise HTTPException(status_code=exc.code, detail=detail or "External API error") from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail=f"External API is unavailable: {exc.reason}") from exc


def to_absolute_url(value: str, base_url: str) -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    if value.startswith(("http://", "https://")):
        return value
    if value.startswith("//"):
        return f"https:{value}"
    return urllib.parse.urljoin(f"{base_url}/", value)


def extract_iframe_url(value: Any, base_url: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith(("http://", "https://", "//")):
        return to_absolute_url(raw, base_url)

    import re

    data_src = re.search(r'data-src=["\']([^"\']+)["\']', raw, flags=re.IGNORECASE)
    if data_src:
        return to_absolute_url(data_src.group(1), base_url)

    src = re.search(r'src=["\']([^"\']+)["\']', raw, flags=re.IGNORECASE)
    if src:
        return to_absolute_url(src.group(1), base_url)

    return ""


def normalize_kinobd_provider_map(provider_map: dict[str, Any]) -> list[dict[str, Any]]:
    players: list[dict[str, Any]] = []
    seen: set[str] = set()

    for provider, value in provider_map.items():
        if not isinstance(value, dict):
            continue
        iframe = extract_iframe_url(value.get("iframe"), KINOBD_API_URL)
        if not iframe or iframe in seen:
            continue
        seen.add(iframe)
        label = str(provider or "KinoBD").upper()
        translate = str(value.get("translate") or label).strip()
        players.append(
            {
                "name": f"KinoBD / {label}",
                "translate": translate,
                "iframe": iframe,
                "quality": str(value.get("quality") or ""),
                "source": "kinobd",
            }
        )

    return players


def normalize_kinobd_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    players: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in rows:
        iframe = extract_iframe_url(item.get("iframe"), KINOBD_API_URL)
        if not iframe or iframe in seen:
            continue
        seen.add(iframe)
        name = item.get("name_russian") or item.get("name_original") or item.get("id") or "KinoBD"
        players.append(
            {
                "name": f"KinoBD / {name}",
                "translate": str(name),
                "iframe": iframe,
                "quality": str(item.get("year") or ""),
                "source": "kinobd",
            }
        )

    return players


def get_kinobd_players(kp_id: str) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "q": kp_id,
        "type": "kp_id",
        "page": 1,
    }
    if KINOBD_TOKEN:
        params["token"] = KINOBD_TOKEN

    search_payload = external_json_request(f"{KINOBD_API_URL}/api/player/search", params=params)
    rows = search_payload.get("data") if isinstance(search_payload, dict) else []
    candidates = rows if isinstance(rows, list) else []
    if not candidates:
        return []

    selected = candidates[0]
    inid = selected.get("id")
    if not inid:
        return normalize_kinobd_candidates(candidates)

    player_url = extract_iframe_url(selected.get("iframe"), KINOBD_API_URL)
    headers = {}
    if player_url:
        headers["X-Re"] = player_url
        try:
            origin = urllib.parse.urlparse(player_url).scheme + "://" + urllib.parse.urlparse(player_url).netloc
            headers["Origin"] = origin
            headers["Referer"] = f"{origin}/"
        except Exception:
            pass

    data = {
        "fast": "1",
        "inid": str(inid),
        "player": KINOBD_PLAYER_PROVIDERS,
    }
    if KINOBD_TOKEN:
        data["token"] = KINOBD_TOKEN

    try:
        playerdata_url = f"{KINOBD_API_URL}/playerdata?cache{urllib.parse.quote(str(inid))}"
        if KINOBD_TOKEN:
            playerdata_url = f"{playerdata_url}&token={urllib.parse.quote(KINOBD_TOKEN)}"
        player_payload = external_form_request(
            playerdata_url,
            data=data,
            headers=headers,
        )
    except Exception:
        return normalize_kinobd_candidates(candidates)

    if isinstance(player_payload, dict):
        players = normalize_kinobd_provider_map(player_payload)
        if players:
            return players

    return normalize_kinobd_candidates(candidates)


def merge_players(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    players: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        for player in group:
            iframe = str(player.get("iframe") or "").strip()
            if not iframe or iframe in seen:
                continue
            seen.add(iframe)
            players.append(player)
    return players


def provider_status(name: str, configured: bool) -> dict[str, Any]:
    return {
        "name": name,
        "configured": configured,
        "ok": False,
        "count": 0,
        "error": "" if configured else "not configured",
    }


app = FastAPI(title=APP_NAME)
app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "app": APP_NAME,
        "kinopoisk": bool(KINOPOISK_API_KEY),
        "kinobd": bool(KINOBD_API_URL),
    }


@app.get("/api/auth/check", dependencies=[Depends(require_admin)])
def check_auth() -> dict[str, Any]:
    return {"ok": True}


@app.get("/api/profiles", dependencies=[Depends(require_admin)])
def list_profiles() -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id, name, avatar, created_at, updated_at
            FROM profiles
            ORDER BY id ASC
            """
        ).fetchall()
        return [dict_from_row(row) for row in rows]


@app.post("/api/profiles", dependencies=[Depends(require_admin)])
def create_profile(payload: ProfileIn) -> dict[str, Any]:
    with db() as conn:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Profile name is required")
        cursor = conn.execute(
            "INSERT INTO profiles(name, avatar) VALUES (?, ?)",
            (name, payload.avatar.strip() or "🙂"),
        )
        row = conn.execute("SELECT * FROM profiles WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict_from_row(row)


@app.delete("/api/profiles/{profile_id}", dependencies=[Depends(require_admin)])
def delete_profile(profile_id: int) -> dict[str, Any]:
    with db() as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM profiles").fetchone()["count"]
        if count <= 1:
            raise HTTPException(status_code=400, detail="Last profile cannot be deleted")
        conn.execute("DELETE FROM movies WHERE profile_id = ?", (profile_id,))
        result = conn.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Profile not found")
        return {"ok": True}


@app.get("/api/movies")
def list_movies(query: str = "", status: str = "all", profile_id: int = 1) -> list[dict[str, Any]]:
    filters = ["profile_id = ?"]
    params: list[Any] = [profile_id]
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
                   source_url, genre, list_status, rating, note, kinopoisk_id, profile_id, created_at, updated_at
            FROM movies
            {where}
            ORDER BY updated_at DESC, id DESC
            """,
            params,
        ).fetchall()
        return [dict_from_row(row) for row in rows]


@app.get("/api/search/kinopoisk")
def search_kinopoisk(query: str) -> list[dict[str, Any]]:
    if not query.strip():
        return []
    payload = kinopoisk_request("/api/v2.1/films/search-by-keyword", {"keyword": query.strip(), "page": 1})
    films = payload.get("films") or []
    return [normalize_kinopoisk_search_item(item) for item in films if item.get("filmId") or item.get("kinopoiskId")]


@app.get("/api/search")
def search_movies(query: str, limit: int = 8) -> list[dict[str, Any]]:
    if not query.strip():
        return []
    safe_limit = max(1, min(limit, 12))
    payload = kinopoisk_request("/api/v2.1/films/search-by-keyword", {"keyword": query.strip(), "page": 1})
    films = payload.get("films") or []
    return [
        normalize_kinopoisk_search_item(item)
        for item in films[:safe_limit]
        if item.get("filmId") or item.get("kinopoiskId")
    ]


@app.get("/api/players/{kp_id}")
def get_players_by_kp_id(kp_id: str) -> dict[str, Any]:
    kp_id = "".join(char for char in str(kp_id) if char.isdigit())
    if not kp_id:
        return {"players": [], "message": "kinopoisk_id is missing"}
    try:
        players = get_kinobd_players(kp_id)
        return {"players": players, "message": "" if players else "no players found"}
    except Exception as exc:
        return {"players": [], "message": str(exc)[:220]}


@app.post("/api/import/kinopoisk/{kp_id}", dependencies=[Depends(require_admin)])
def import_kinopoisk_movie(kp_id: int, profile_id: int = 1) -> dict[str, Any]:
    payload = kinopoisk_request(f"/api/v2.2/films/{kp_id}")
    movie = normalize_kinopoisk_film(payload)
    with db() as conn:
        existing = conn.execute(
            "SELECT * FROM movies WHERE profile_id = ? AND source_url = ?",
            (profile_id, movie["source_url"]),
        ).fetchone()
        if existing:
            return dict_from_row(existing)
        cursor = conn.execute(
            """
            INSERT INTO movies(profile_id, kinopoisk_id, title, original_title, year, description, poster_url, player_url, source_url, genre)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile_id,
                movie["kinopoisk_id"],
                movie["title"],
                movie["original_title"],
                movie["year"],
                movie["description"],
                movie["poster_url"],
                movie["player_url"],
                movie["source_url"],
                movie["genre"],
            ),
        )
        row = conn.execute("SELECT * FROM movies WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict_from_row(row)


@app.post("/api/movies", dependencies=[Depends(require_admin)])
def create_movie(payload: MovieIn) -> dict[str, Any]:
    with db() as conn:
        profile = conn.execute("SELECT id FROM profiles WHERE id = ?", (payload.profile_id,)).fetchone()
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        if payload.kinopoisk_id:
            existing = conn.execute(
                "SELECT * FROM movies WHERE profile_id = ? AND kinopoisk_id = ?",
                (payload.profile_id, payload.kinopoisk_id),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE movies
                    SET player_url = ?, list_status = ?
                    WHERE id = ?
                    """,
                    (payload.player_url, payload.list_status, existing["id"]),
                )
                row = conn.execute("SELECT * FROM movies WHERE id = ?", (existing["id"],)).fetchone()
                return dict_from_row(row)

        cursor = conn.execute(
            """
            INSERT INTO movies(profile_id, kinopoisk_id, title, original_title, year, description, poster_url, player_url, source_url, genre, list_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.profile_id,
                payload.kinopoisk_id,
                payload.title,
                payload.original_title,
                payload.year,
                payload.description,
                payload.poster_url,
                payload.player_url,
                payload.source_url,
                payload.genre,
                payload.list_status,
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


@app.get("/api/movies/{movie_id}/players")
def get_movie_players(movie_id: int) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT kinopoisk_id, title FROM movies WHERE id = ?", (movie_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Movie not found")

    kp_id = str(row["kinopoisk_id"] or "").strip()
    if not kp_id:
        return {
            "players": [],
            "providers": [],
            "message": "kinopoisk_id is missing",
        }

    kinobd_players: list[dict[str, Any]] = []
    statuses = [
        provider_status("KinoBD", bool(KINOBD_API_URL)),
    ]

    try:
        kinobd_players = get_kinobd_players(kp_id)
        statuses[0]["ok"] = True
        statuses[0]["count"] = len(kinobd_players)
        statuses[0]["error"] = ""
    except Exception as exc:
        statuses[0]["error"] = str(exc)[:220]
        kinobd_players = []

    players = merge_players(kinobd_players)
    return {
        "players": players,
        "providers": statuses,
        "message": "" if players else "no players found",
    }


@app.put("/api/movies/{movie_id}/player", dependencies=[Depends(require_admin)])
def update_player(movie_id: int, payload: PlayerUpdate) -> dict[str, Any]:
    with db() as conn:
        result = conn.execute(
            "UPDATE movies SET player_url = ? WHERE id = ?",
            (payload.player_url, movie_id),
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Movie not found")
        return {"ok": True, "player_url": payload.player_url}


@app.delete("/api/movies/{movie_id}", dependencies=[Depends(require_admin)])
def delete_movie(movie_id: int) -> dict[str, Any]:
    with db() as conn:
        result = conn.execute("DELETE FROM movies WHERE id = ?", (movie_id,))
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
