from __future__ import annotations

import base64
import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import sqlite3
import time
from datetime import datetime, timedelta
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
DB_PATH = Path(os.environ.get("DATABASE_PATH", ROOT / "database" / "myjnia.sqlite"))
SCHEMA_PATH = ROOT / "database" / "schema.sql"
SEED_PATH = ROOT / "database" / "seed.sql"
SESSION_COOKIE = "myjnia_session"
SESSION_SECONDS = 60 * 60 * 12
PASSWORD_ITERATIONS = 260_000
PASSWORD_RESET_SECONDS = 60 * 30
SESSIONS: dict[str, dict] = {}
BOOKING_STATUSES = {
    "new",
    "confirmed",
    "in_progress",
    "completed",
    "cancelled",
    "no_show",
}
STATUS_NOTIFICATION_LABELS = {
    "new": "nowa",
    "confirmed": "potwierdzona",
    "in_progress": "w trakcie realizacji",
    "completed": "zakonczona",
    "cancelled": "anulowana",
    "no_show": "brak obecnosci",
}
SLOT_INTERVAL_MINUTES = 30
MIN_BOOKING_NOTICE_MINUTES = 60
DEFAULT_WORKING_HOURS = {
    0: ("08:00", "18:00"),
    1: ("08:00", "18:00"),
    2: ("08:00", "18:00"),
    3: ("08:00", "18:00"),
    4: ("08:00", "18:00"),
    5: ("09:00", "15:00"),
}
DEFAULT_CLOSED_HOURS = ("09:00", "15:00")
DEFAULT_STATION_COUNT = 1
MAX_STATION_COUNT = 6


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_database_if_missing() -> None:
    if DB_PATH.exists():
        return

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        if SEED_PATH.exists():
            conn.executescript(SEED_PATH.read_text(encoding="utf-8"))
        conn.commit()


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(row) for row in rows]


def require_owner(user: dict | None) -> None:
    if not user or user["role"] != "owner":
        raise ApiError("Dostep tylko dla wlasciciela.", 403)


def require_client(user: dict | None) -> None:
    if not user or user["role"] != "client":
        raise ApiError("Dostep tylko dla klienta.", 403)


def parse_json_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0") or 0)
    if length == 0:
        return {}

    try:
        return json.loads(handler.rfile.read(length).decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ApiError("Nieprawidlowy format danych.") from exc


def split_name(full_name: str) -> tuple[str, str]:
    parts = [part for part in full_name.strip().split(" ") if part]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], "-"
    return parts[0], " ".join(parts[1:])


def parse_booking_start(value: str) -> datetime:
    if not value:
        raise ApiError("Wybierz termin wizyty.")

    normalized = value.replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    raise ApiError("Termin ma nieprawidlowy format.")


def parse_booking_date(value: str) -> datetime.date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError) as exc:
        raise ApiError("Wybierz poprawny dzien wizyty.") from exc


def normalize_time_value(value: object) -> str:
    text = str(value or "").strip()
    try:
        return datetime.strptime(text, "%H:%M").strftime("%H:%M")
    except ValueError as exc:
        raise ApiError("Podaj poprawna godzine w formacie HH:MM.") from exc


def parse_ids(value: object) -> list[int]:
    if value is None:
        return []

    values = value if isinstance(value, list) else [value]
    ids: list[int] = []
    seen: set[int] = set()
    for item in values:
        for piece in str(item).split(","):
            piece = piece.strip()
            if not piece.isdigit():
                continue
            number = int(piece)
            if number > 0 and number not in seen:
                ids.append(number)
                seen.add(number)
    return ids


def load_station_count(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT value FROM site_settings WHERE key = 'station_count'",
    ).fetchone()
    try:
        value = int(row["value"]) if row else DEFAULT_STATION_COUNT
    except (TypeError, ValueError):
        value = DEFAULT_STATION_COUNT
    return min(max(value, 1), MAX_STATION_COUNT)


def load_day_schedule(conn: sqlite3.Connection, day: datetime.date) -> dict:
    station_count = load_station_count(conn)
    closure = conn.execute(
        """
        SELECT reason
        FROM business_closures
        WHERE date = ?
        """,
        (day.strftime("%Y-%m-%d"),),
    ).fetchone()
    if closure:
        return {
            "weekday": day.weekday(),
            "is_open": False,
            "opens_at": None,
            "closes_at": None,
            "station_count": station_count,
            "closed_reason": closure["reason"] or "Dzien wolny",
        }

    hours = conn.execute(
        """
        SELECT weekday, is_open, opens_at, closes_at
        FROM business_hours
        WHERE weekday = ?
        """,
        (day.weekday(),),
    ).fetchone()

    if hours is None:
        default = DEFAULT_WORKING_HOURS.get(day.weekday())
        if default is None:
            opens_at, closes_at = DEFAULT_CLOSED_HOURS
            is_open = False
        else:
            opens_at, closes_at = default
            is_open = True
    else:
        opens_at = hours["opens_at"]
        closes_at = hours["closes_at"]
        is_open = bool(hours["is_open"])

    return {
        "weekday": day.weekday(),
        "is_open": is_open,
        "opens_at": opens_at if is_open else None,
        "closes_at": closes_at if is_open else None,
        "station_count": station_count,
        "closed_reason": "" if is_open else "Zamkniete",
    }


def working_window(
    conn: sqlite3.Connection,
    day: datetime.date,
) -> tuple[datetime, datetime, dict] | None:
    schedule = load_day_schedule(conn, day)
    if not schedule["is_open"]:
        return None
    return (
        datetime.strptime(f"{day} {schedule['opens_at']}", "%Y-%m-%d %H:%M"),
        datetime.strptime(f"{day} {schedule['closes_at']}", "%Y-%m-%d %H:%M"),
        schedule,
    )


def validate_booking_window(
    conn: sqlite3.Connection,
    starts_at: datetime,
    duration_minutes: int,
) -> int:
    if starts_at.minute % SLOT_INTERVAL_MINUTES or starts_at.second or starts_at.microsecond:
        raise ApiError("Wybierz godzine z kalendarza rezerwacji.")

    window = working_window(conn, starts_at.date())
    if window is None:
        raise ApiError("Myjnia jest zamknieta w wybranym dniu.")

    opens_at, closes_at, schedule = window
    ends_at = starts_at + timedelta(minutes=max(duration_minutes, 15))
    if starts_at < opens_at or ends_at > closes_at:
        raise ApiError("Wybrany termin wykracza poza godziny pracy myjni.")

    if starts_at < datetime.now() + timedelta(minutes=MIN_BOOKING_NOTICE_MINUTES):
        raise ApiError("Wybierz termin z przynajmniej godzinnym wyprzedzeniem.")

    return int(schedule["station_count"])


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return (
        "pbkdf2_sha256$"
        f"{PASSWORD_ITERATIONS}$"
        f"{base64.b64encode(salt).decode('ascii')}$"
        f"{base64.b64encode(digest).decode('ascii')}"
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, iterations, salt, expected = stored_hash.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        calculated = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            base64.b64decode(salt),
            int(iterations),
        )
        return hmac.compare_digest(calculated, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False


def hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def ensure_auth_schema() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              email TEXT NOT NULL UNIQUE,
              phone TEXT,
              password_hash TEXT NOT NULL,
              role TEXT NOT NULL CHECK (role IN ('owner', 'client')),
              customer_id INTEGER,
              is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_app_users_role
              ON app_users (role, is_active)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_app_users_customer
              ON app_users (customer_id)
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_app_users_updated_at
            AFTER UPDATE ON app_users
            FOR EACH ROW
            WHEN NEW.updated_at = OLD.updated_at
            BEGIN
              UPDATE app_users
              SET updated_at = strftime('%Y-%m-%d %H:%M:%f', 'now')
              WHERE id = OLD.id;
            END
            """
        )
        ensure_demo_accounts(conn)
        conn.commit()


def ensure_schedule_schema() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS business_hours (
              weekday INTEGER PRIMARY KEY CHECK (weekday BETWEEN 0 AND 6),
              is_open INTEGER NOT NULL DEFAULT 1 CHECK (is_open IN (0, 1)),
              opens_at TEXT NOT NULL,
              closes_at TEXT NOT NULL,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS business_closures (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              date TEXT NOT NULL UNIQUE,
              reason TEXT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for weekday in range(7):
            default_hours = DEFAULT_WORKING_HOURS.get(weekday)
            is_open = 1 if default_hours else 0
            opens_at, closes_at = default_hours or DEFAULT_CLOSED_HOURS
            conn.execute(
                """
                INSERT OR IGNORE INTO business_hours (
                  weekday, is_open, opens_at, closes_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (weekday, is_open, opens_at, closes_at),
            )
        conn.execute(
            """
            INSERT INTO site_settings (key, value)
            VALUES ('station_count', ?)
            ON CONFLICT(key) DO NOTHING
            """,
            (str(DEFAULT_STATION_COUNT),),
        )
        conn.commit()


def ensure_notification_schema() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS client_notifications (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              customer_id INTEGER NOT NULL,
              booking_id INTEGER,
              type TEXT NOT NULL,
              title TEXT NOT NULL,
              message TEXT NOT NULL,
              is_read INTEGER NOT NULL DEFAULT 0 CHECK (is_read IN (0, 1)),
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              read_at TEXT,
              FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
              FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE SET NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_client_notifications_customer
              ON client_notifications (customer_id, is_read, created_at)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_client_notifications_booking
              ON client_notifications (booking_id)
            """
        )
        conn.commit()


def ensure_account_recovery_schema() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              token_hash TEXT NOT NULL UNIQUE,
              expires_at TEXT NOT NULL,
              used_at TEXT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY (user_id) REFERENCES app_users(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user
              ON password_reset_tokens (user_id, used_at, expires_at)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS external_auth_accounts (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              provider TEXT NOT NULL CHECK (provider IN ('google', 'apple')),
              provider_subject TEXT NOT NULL,
              email TEXT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY (user_id) REFERENCES app_users(id) ON DELETE CASCADE,
              UNIQUE (provider, provider_subject),
              UNIQUE (user_id, provider)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_external_auth_accounts_user
              ON external_auth_accounts (user_id)
            """
        )
        conn.commit()


def ensure_demo_accounts(conn: sqlite3.Connection) -> None:
    owner = conn.execute(
        "SELECT id FROM app_users WHERE email = ?",
        ("owner@myjnia.local",),
    ).fetchone()
    if owner is None:
        conn.execute(
            """
            INSERT INTO app_users (name, email, phone, password_hash, role)
            VALUES (?, ?, ?, ?, 'owner')
            """,
            (
                "Wlasciciel AutoClean",
                "owner@myjnia.local",
                "+48 123 456 789",
                hash_password("owner123"),
            ),
        )

    customer = conn.execute(
        "SELECT id FROM customers WHERE email = ?",
        ("anna.kowalska@example.com",),
    ).fetchone()
    customer_id = customer["id"] if customer else None
    client = conn.execute(
        "SELECT id FROM app_users WHERE email = ?",
        ("anna.kowalska@example.com",),
    ).fetchone()
    if client is None and customer_id is not None:
        conn.execute(
            """
            INSERT INTO app_users (
              name, email, phone, password_hash, role, customer_id
            )
            VALUES (?, ?, ?, ?, 'client', ?)
            """,
            (
                "Anna Kowalska",
                "anna.kowalska@example.com",
                "+48 501 222 333",
                hash_password("klient123"),
                customer_id,
            ),
        )


def serialize_user(row: sqlite3.Row | dict | None) -> dict | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "phone": row["phone"] or "",
        "role": row["role"],
        "customer_id": row["customer_id"],
    }


def load_user_by_id(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT id, name, email, phone, role, customer_id
        FROM app_users
        WHERE id = ? AND is_active = 1
        """,
        (user_id,),
    ).fetchone()


def session_token_from_request(handler: BaseHTTPRequestHandler) -> str | None:
    header = handler.headers.get("Cookie", "")
    if not header:
        return None
    jar = cookies.SimpleCookie()
    jar.load(header)
    morsel = jar.get(SESSION_COOKIE)
    return morsel.value if morsel else None


def current_user(handler: BaseHTTPRequestHandler) -> dict | None:
    token = session_token_from_request(handler)
    if not token:
        return None
    session = SESSIONS.get(token)
    if not session or session["expires_at"] < time.time():
        SESSIONS.pop(token, None)
        return None

    session["expires_at"] = time.time() + SESSION_SECONDS
    with connect() as conn:
        return serialize_user(load_user_by_id(conn, session["user_id"]))


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    SESSIONS[token] = {
        "user_id": user_id,
        "expires_at": time.time() + SESSION_SECONDS,
    }
    return token


def clear_session(handler: BaseHTTPRequestHandler) -> None:
    token = session_token_from_request(handler)
    if token:
        SESSIONS.pop(token, None)


def session_cookie(token: str, max_age: int = SESSION_SECONDS) -> str:
    return (
        f"{SESSION_COOKIE}={token}; HttpOnly; Path=/; "
        f"SameSite=Lax; Max-Age={max_age}"
    )


def expired_session_cookie() -> str:
    return f"{SESSION_COOKIE}=; HttpOnly; Path=/; SameSite=Lax; Max-Age=0"


def load_services(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, name, slug, description, duration_minutes, base_price_pln
        FROM services
        WHERE is_active = 1
        ORDER BY display_order, id
        """
    ).fetchall()
    return rows_to_dicts(rows)


def load_addons(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, name, description, duration_minutes, price_pln
        FROM service_addons
        WHERE is_active = 1
        ORDER BY id
        """
    ).fetchall()
    return rows_to_dicts(rows)


def load_settings(conn: sqlite3.Connection) -> dict:
    rows = conn.execute("SELECT key, value FROM site_settings").fetchall()
    return {row["key"]: row["value"] for row in rows}


def load_owner_schedule(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        """
        SELECT weekday, is_open, opens_at, closes_at
        FROM business_hours
        ORDER BY weekday
        """
    ).fetchall()
    hours_by_day = {row["weekday"]: dict(row) for row in rows}
    hours = []
    for weekday in range(7):
        default = DEFAULT_WORKING_HOURS.get(weekday) or DEFAULT_CLOSED_HOURS
        row = hours_by_day.get(weekday)
        hours.append(
            {
                "weekday": weekday,
                "is_open": bool(row["is_open"]) if row else weekday in DEFAULT_WORKING_HOURS,
                "opens_at": row["opens_at"] if row else default[0],
                "closes_at": row["closes_at"] if row else default[1],
            }
        )

    closures = conn.execute(
        """
        SELECT id, date, reason
        FROM business_closures
        ORDER BY date(date), id
        LIMIT 40
        """
    ).fetchall()
    return {
        "hours": hours,
        "closures": rows_to_dicts(closures),
        "station_count": load_station_count(conn),
    }


def load_bookings(
    conn: sqlite3.Connection,
    customer_id: int | None = None,
    include_history: bool = False,
    date_value: str | None = None,
) -> list[dict]:
    conditions = []
    params: list[object] = []
    if date_value:
        parse_booking_date(date_value)
        conditions.append("date(b.starts_at) = date(?)")
        params.append(date_value)
    elif not include_history:
        conditions.append("datetime(b.starts_at) >= datetime('now', '-2 days')")
    if customer_id is not None:
        conditions.append("b.customer_id = ?")
        params.append(customer_id)
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    limit_clause = "LIMIT 60" if date_value else "LIMIT 30"

    rows = conn.execute(
        f"""
        SELECT
          b.id,
          b.starts_at,
          b.ends_at,
          b.status,
          b.total_price_pln,
          b.customer_notes,
          c.first_name || ' ' || c.last_name AS customer_name,
          c.email,
          c.phone,
          b.vehicle_id,
          COALESCE(v.registration_number, '') AS registration_number,
          TRIM(COALESCE(v.brand, '') || ' ' || COALESCE(v.model, '')) AS vehicle,
          COALESCE(GROUP_CONCAT(DISTINCT s.name), '') AS services,
          COALESCE(GROUP_CONCAT(DISTINCT a.name), '') AS addons,
          CASE
            WHEN b.status IN ('new', 'confirmed') AND datetime(b.starts_at) > datetime('now')
            THEN 1
            ELSE 0
          END AS can_cancel
        FROM bookings b
        JOIN customers c ON c.id = b.customer_id
        LEFT JOIN vehicles v ON v.id = b.vehicle_id
        LEFT JOIN booking_services bs ON bs.booking_id = b.id
        LEFT JOIN services s ON s.id = bs.service_id
        LEFT JOIN booking_addons ba ON ba.booking_id = b.id
        LEFT JOIN service_addons a ON a.id = ba.addon_id
        {where_clause}
        GROUP BY b.id
        ORDER BY datetime(b.starts_at)
        {limit_clause}
        """,
        params,
    ).fetchall()
    return rows_to_dicts(rows)


def load_selected_booking_items(
    conn: sqlite3.Connection,
    service_ids: list[int],
    addon_ids: list[int],
) -> dict:
    service_ids = parse_ids(service_ids)
    addon_ids = parse_ids(addon_ids)
    if not service_ids:
        raise ApiError("Wybierz przynajmniej jedna usluge.")

    placeholders = ",".join("?" for _ in service_ids)
    services = conn.execute(
        f"""
        SELECT id, name, base_price_pln, duration_minutes
        FROM services
        WHERE is_active = 1 AND id IN ({placeholders})
        """,
        service_ids,
    ).fetchall()
    if len(services) != len(set(service_ids)):
        raise ApiError("Wybrana usluga nie jest juz dostepna.")

    addons = []
    if addon_ids:
        addon_placeholders = ",".join("?" for _ in addon_ids)
        addons = conn.execute(
            f"""
                SELECT id, name, price_pln, duration_minutes
            FROM service_addons
            WHERE is_active = 1 AND id IN ({addon_placeholders})
            """,
            addon_ids,
        ).fetchall()
        if len(addons) != len(set(addon_ids)):
            raise ApiError("Wybrany dodatek nie jest juz dostepny.")

    duration = sum(int(row["duration_minutes"]) for row in services)
    duration += sum(int(row["duration_minutes"]) for row in addons)
    total = sum(float(row["base_price_pln"]) for row in services)
    total += sum(float(row["price_pln"]) for row in addons)
    return {
        "services": services,
        "addons": addons,
        "duration_minutes": max(duration, 15),
        "total_price_pln": round(total, 2),
    }


def remaining_capacity(
    conn: sqlite3.Connection,
    starts_at: datetime,
    ends_at: datetime,
    station_count: int,
) -> int:
    rows = conn.execute(
        """
        SELECT starts_at, ends_at
        FROM bookings
        WHERE status NOT IN ('cancelled', 'no_show')
          AND datetime(starts_at) < datetime(?)
          AND datetime(ends_at) > datetime(?)
        """,
        (
            ends_at.strftime("%Y-%m-%d %H:%M:%S"),
            starts_at.strftime("%Y-%m-%d %H:%M:%S"),
        ),
    ).fetchall()
    if not rows:
        return station_count

    points = {starts_at, ends_at}
    intervals = []
    for row in rows:
        booking_start = datetime.strptime(row["starts_at"], "%Y-%m-%d %H:%M:%S")
        booking_end = datetime.strptime(row["ends_at"], "%Y-%m-%d %H:%M:%S")
        intervals.append((booking_start, booking_end))
        if starts_at < booking_start < ends_at:
            points.add(booking_start)
        if starts_at < booking_end < ends_at:
            points.add(booking_end)

    ordered = sorted(points)
    minimum_remaining = station_count
    for index, segment_start in enumerate(ordered[:-1]):
        segment_end = ordered[index + 1]
        active = sum(
            1
            for booking_start, booking_end in intervals
            if booking_start < segment_end and booking_end > segment_start
        )
        minimum_remaining = min(minimum_remaining, station_count - active)
    return max(minimum_remaining, 0)


def has_booking_conflict(
    conn: sqlite3.Connection,
    starts_at: datetime,
    ends_at: datetime,
    station_count: int,
) -> bool:
    return remaining_capacity(conn, starts_at, ends_at, station_count) <= 0


def load_availability(
    conn: sqlite3.Connection,
    day_value: str,
    service_ids: list[int],
    addon_ids: list[int],
) -> dict:
    day = parse_booking_date(day_value)
    items = load_selected_booking_items(conn, service_ids, addon_ids)
    duration = int(items["duration_minutes"])
    schedule = load_day_schedule(conn, day)
    window = working_window(conn, day)
    bookings = load_bookings(conn, include_history=True, date_value=day_value)

    if window is None:
        return {
            "date": day_value,
            "duration_minutes": duration,
            "workday": {
                "is_open": False,
                "open_at": None,
                "close_at": None,
                "station_count": schedule["station_count"],
                "closed_reason": schedule["closed_reason"],
            },
            "slots": [],
            "bookings": bookings,
        }

    opens_at, closes_at, schedule = window
    cutoff = datetime.now() + timedelta(minutes=MIN_BOOKING_NOTICE_MINUTES)
    slot = opens_at
    slots = []
    while slot + timedelta(minutes=duration) <= closes_at:
        ends_at = slot + timedelta(minutes=duration)
        capacity = remaining_capacity(conn, slot, ends_at, int(schedule["station_count"]))
        available = slot >= cutoff and capacity > 0
        reason = ""
        if slot < cutoff:
            reason = "za pozno"
        elif not available:
            reason = "zajety"
        slots.append(
            {
                "starts_at": slot.strftime("%Y-%m-%d %H:%M:%S"),
                "ends_at": ends_at.strftime("%Y-%m-%d %H:%M:%S"),
                "time": slot.strftime("%H:%M"),
                "available": available,
                "remaining_capacity": capacity,
                "reason": reason,
            }
        )
        slot += timedelta(minutes=SLOT_INTERVAL_MINUTES)

    return {
        "date": day_value,
        "duration_minutes": duration,
        "workday": {
            "is_open": True,
            "open_at": opens_at.strftime("%H:%M"),
            "close_at": closes_at.strftime("%H:%M"),
            "station_count": schedule["station_count"],
            "closed_reason": "",
        },
        "slots": slots,
        "bookings": bookings,
    }


def load_dashboard(conn: sqlite3.Connection) -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    rows = conn.execute(
        """
        SELECT status, COUNT(*) AS count
        FROM bookings
        GROUP BY status
        """
    ).fetchall()
    today_count = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM bookings
        WHERE date(starts_at) = date(?)
        """,
        (today,),
    ).fetchone()["count"]
    revenue = conn.execute(
        """
        SELECT COALESCE(SUM(total_price_pln), 0) AS total
        FROM bookings
        WHERE status IN ('confirmed', 'in_progress', 'completed')
        """
    ).fetchone()["total"]
    customer_count = conn.execute(
        "SELECT COUNT(*) AS count FROM customers",
    ).fetchone()["count"]
    unread_messages = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM contact_messages
        WHERE status IN ('new', 'read')
        """,
    ).fetchone()["count"]
    pending_payments = conn.execute(
        """
        SELECT COALESCE(SUM(amount_pln), 0) AS total
        FROM payments
        WHERE status = 'pending'
        """,
    ).fetchone()["total"]
    week_count = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM bookings
        WHERE date(starts_at) >= date(?)
          AND date(starts_at) < date(?, '+7 days')
          AND status NOT IN ('cancelled', 'no_show')
        """,
        (today, today),
    ).fetchone()["count"]

    return {
        "by_status": {row["status"]: row["count"] for row in rows},
        "today_count": today_count,
        "revenue_pln": revenue,
        "customer_count": customer_count,
        "unread_messages": unread_messages,
        "pending_payments_pln": pending_payments,
        "week_count": week_count,
    }


def load_public_dashboard(conn: sqlite3.Connection) -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    today_count = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM bookings
        WHERE date(starts_at) = date(?)
          AND status NOT IN ('cancelled', 'no_show')
        """,
        (today,),
    ).fetchone()["count"]
    next_booking = conn.execute(
        """
        SELECT starts_at
        FROM bookings
        WHERE datetime(starts_at) >= datetime('now')
          AND status NOT IN ('cancelled', 'no_show')
        ORDER BY datetime(starts_at)
        LIMIT 1
        """
    ).fetchone()

    return {
        "today_count": today_count,
        "next_slot": next_booking["starts_at"] if next_booking else None,
    }


def load_recent_messages(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, name, email, phone, subject, message, status, created_at
        FROM contact_messages
        ORDER BY datetime(created_at) DESC
        LIMIT 5
        """
    ).fetchall()
    return rows_to_dicts(rows)


def load_client_profile(conn: sqlite3.Connection, user: dict) -> dict:
    customer = None
    if user.get("customer_id"):
        customer = conn.execute(
            """
            SELECT id, first_name, last_name, email, phone, marketing_consent
            FROM customers
            WHERE id = ?
            """,
            (user["customer_id"],),
        ).fetchone()

    return {
        "name": user["name"],
        "email": user["email"],
        "phone": user.get("phone") or (customer["phone"] if customer else ""),
        "marketing_consent": bool(customer["marketing_consent"]) if customer else False,
    }


def load_client_vehicles(conn: sqlite3.Connection, customer_id: int | None) -> list[dict]:
    if not customer_id:
        return []
    rows = conn.execute(
        """
        SELECT id, registration_number, brand, model, vehicle_size, color
        FROM vehicles
        WHERE customer_id = ?
        ORDER BY datetime(created_at) DESC, id DESC
        """,
        (customer_id,),
    ).fetchall()
    return rows_to_dicts(rows)


def load_client_notifications(
    conn: sqlite3.Connection,
    customer_id: int | None,
) -> dict:
    if not customer_id:
        return {"items": [], "unread_count": 0}

    rows = conn.execute(
        """
        SELECT
          n.id,
          n.booking_id,
          n.type,
          n.title,
          n.message,
          n.is_read,
          n.created_at,
          n.read_at,
          b.starts_at,
          b.status AS booking_status
        FROM client_notifications n
        LEFT JOIN bookings b ON b.id = n.booking_id
        WHERE n.customer_id = ?
        ORDER BY datetime(n.created_at) DESC, n.id DESC
        LIMIT 30
        """,
        (customer_id,),
    ).fetchall()
    unread_count = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM client_notifications
        WHERE customer_id = ? AND is_read = 0
        """,
        (customer_id,),
    ).fetchone()["count"]
    return {"items": rows_to_dicts(rows), "unread_count": unread_count}


def create_client_notification(
    conn: sqlite3.Connection,
    customer_id: int,
    booking_id: int | None,
    notification_type: str,
    title: str,
    message: str,
) -> None:
    conn.execute(
        """
        INSERT INTO client_notifications (
          customer_id, booking_id, type, title, message
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (customer_id, booking_id, notification_type, title, message),
    )


def bootstrap_payload(user: dict | None) -> dict:
    with connect() as conn:
        payload = {
            "services": load_services(conn),
            "addons": load_addons(conn),
            "settings": load_settings(conn),
            "current_user": user,
            "bookings": [],
            "my_bookings": [],
            "owner_messages": [],
            "client_profile": None,
            "client_vehicles": [],
            "client_notifications": {"items": [], "unread_count": 0},
            "owner_day_plan": [],
            "owner_schedule": None,
            "dashboard": load_public_dashboard(conn),
        }

        if user and user["role"] == "owner":
            payload["bookings"] = load_bookings(conn)
            payload["dashboard"] = load_dashboard(conn)
            payload["owner_messages"] = load_recent_messages(conn)
            payload["owner_schedule"] = load_owner_schedule(conn)
            payload["owner_day_plan"] = load_bookings(
                conn,
                include_history=True,
                date_value=datetime.now().strftime("%Y-%m-%d"),
            )
        elif user and user["role"] == "client" and user["customer_id"]:
            payload["my_bookings"] = load_bookings(conn, user["customer_id"], include_history=True)
            payload["client_profile"] = load_client_profile(conn, user)
            payload["client_vehicles"] = load_client_vehicles(conn, user["customer_id"])
            payload["client_notifications"] = load_client_notifications(conn, user["customer_id"])

        return payload


def register_client(payload: dict) -> dict:
    full_name = str(payload.get("name", "")).strip()
    email = str(payload.get("email", "")).strip().lower()
    phone = str(payload.get("phone", "")).strip()
    password = str(payload.get("password", ""))

    if not full_name:
        raise ApiError("Podaj imie i nazwisko.")
    if "@" not in email or "." not in email:
        raise ApiError("Podaj poprawny adres e-mail.")
    if len(phone) < 7:
        raise ApiError("Podaj numer telefonu.")
    if len(password) < 6:
        raise ApiError("Haslo musi miec przynajmniej 6 znakow.")

    first_name, last_name = split_name(full_name)
    with connect() as conn:
        existing = conn.execute(
            "SELECT id FROM app_users WHERE email = ?",
            (email,),
        ).fetchone()
        if existing:
            raise ApiError("Konto z tym adresem juz istnieje.")

        conn.execute(
            """
            INSERT INTO customers (first_name, last_name, email, phone)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
              first_name = excluded.first_name,
              last_name = excluded.last_name,
              phone = excluded.phone
            """,
            (first_name, last_name, email, phone),
        )
        customer_id = conn.execute(
            "SELECT id FROM customers WHERE email = ?",
            (email,),
        ).fetchone()["id"]
        cursor = conn.execute(
            """
            INSERT INTO app_users (
              name, email, phone, password_hash, role, customer_id
            )
            VALUES (?, ?, ?, ?, 'client', ?)
            """,
            (full_name, email, phone, hash_password(password), customer_id),
        )
        conn.commit()
        user = load_user_by_id(conn, cursor.lastrowid)
        return serialize_user(user)


def login_user(payload: dict) -> dict:
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))
    if not email or not password:
        raise ApiError("Podaj e-mail i haslo.")

    with connect() as conn:
        row = conn.execute(
            """
            SELECT id, name, email, phone, password_hash, role, customer_id
            FROM app_users
            WHERE email = ? AND is_active = 1
            """,
            (email,),
        ).fetchone()
        if row is None or not verify_password(password, row["password_hash"]):
            raise ApiError("Nieprawidlowy e-mail lub haslo.", 401)
        return serialize_user(row)


def request_password_reset(payload: dict) -> dict:
    email = str(payload.get("email", "")).strip().lower()
    if "@" not in email or "." not in email:
        raise ApiError("Podaj poprawny adres e-mail.")

    with connect() as conn:
        user = conn.execute(
            """
            SELECT id
            FROM app_users
            WHERE email = ? AND is_active = 1
            """,
            (email,),
        ).fetchone()
        reset_token = ""
        if user:
            reset_token = secrets.token_urlsafe(8)
            expires_at = datetime.now() + timedelta(seconds=PASSWORD_RESET_SECONDS)
            conn.execute(
                """
                UPDATE password_reset_tokens
                SET used_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND used_at IS NULL
                """,
                (user["id"],),
            )
            conn.execute(
                """
                INSERT INTO password_reset_tokens (
                  user_id, token_hash, expires_at
                )
                VALUES (?, ?, ?)
                """,
                (
                    user["id"],
                    hash_reset_token(reset_token),
                    expires_at.strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
            conn.commit()

    return {
        "message": "Jesli konto istnieje, kod resetu zostal przygotowany.",
        "reset_token": reset_token,
        "expires_in_minutes": PASSWORD_RESET_SECONDS // 60,
    }


def complete_password_reset(payload: dict) -> dict:
    email = str(payload.get("email", "")).strip().lower()
    reset_token = str(payload.get("reset_token", "")).strip()
    password = str(payload.get("password", ""))

    if "@" not in email or "." not in email:
        raise ApiError("Podaj poprawny adres e-mail.")
    if not reset_token:
        raise ApiError("Podaj kod resetu.")
    if len(password) < 6:
        raise ApiError("Haslo musi miec przynajmniej 6 znakow.")

    with connect() as conn:
        user = conn.execute(
            """
            SELECT id
            FROM app_users
            WHERE email = ? AND is_active = 1
            """,
            (email,),
        ).fetchone()
        if user is None:
            raise ApiError("Kod resetu jest nieprawidlowy albo wygasl.", 401)

        token = conn.execute(
            """
            SELECT id
            FROM password_reset_tokens
            WHERE user_id = ?
              AND token_hash = ?
              AND used_at IS NULL
              AND datetime(expires_at) >= datetime('now')
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT 1
            """,
            (user["id"], hash_reset_token(reset_token)),
        ).fetchone()
        if token is None:
            raise ApiError("Kod resetu jest nieprawidlowy albo wygasl.", 401)

        conn.execute(
            """
            UPDATE app_users
            SET password_hash = ?
            WHERE id = ?
            """,
            (hash_password(password), user["id"]),
        )
        conn.execute(
            """
            UPDATE password_reset_tokens
            SET used_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (token["id"],),
        )
        conn.commit()

    for session_token, session in list(SESSIONS.items()):
        if session.get("user_id") == user["id"]:
            SESSIONS.pop(session_token, None)

    return {"ok": True, "message": "Haslo zostalo zmienione. Mozesz sie zalogowac."}


def customer_for_booking(
    conn: sqlite3.Connection,
    payload: dict,
    user: dict,
) -> tuple[int, str, str, str, str]:
    if user["role"] == "client":
        full_name = user["name"]
        email = user["email"]
        phone = str(payload.get("phone") or user.get("phone") or "").strip()
    else:
        full_name = str(payload.get("name", "")).strip()
        email = str(payload.get("email", "")).strip().lower()
        phone = str(payload.get("phone", "")).strip()

    if not full_name:
        raise ApiError("Podaj imie i nazwisko.")
    if "@" not in email or "." not in email:
        raise ApiError("Podaj poprawny adres e-mail.")
    if len(phone) < 7:
        raise ApiError("Podaj numer telefonu.")

    first_name, last_name = split_name(full_name)
    conn.execute(
        """
        INSERT INTO customers (first_name, last_name, email, phone, marketing_consent)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(email) DO UPDATE SET
          first_name = excluded.first_name,
          last_name = excluded.last_name,
          phone = excluded.phone,
          marketing_consent = excluded.marketing_consent
        """,
        (
            first_name,
            last_name,
            email,
            phone,
            1 if payload.get("marketing_consent") else 0,
        ),
    )
    customer_id = conn.execute(
        "SELECT id FROM customers WHERE email = ?",
        (email,),
    ).fetchone()["id"]

    if user["role"] == "client":
        conn.execute(
            """
            UPDATE app_users
            SET phone = ?, customer_id = ?
            WHERE id = ?
            """,
            (phone, customer_id, user["id"]),
        )

    return customer_id, full_name, email, phone, first_name


def create_booking(payload: dict, user: dict | None) -> dict:
    if user is None:
        raise ApiError("Zaloguj sie, aby zapisac rezerwacje.", 401)
    if user["role"] != "client":
        raise ApiError("Konto wlasciciela sluzy do obslugi wizyt, nie do rezerwacji.", 403)

    service_ids = parse_ids(payload.get("service_ids", []))
    addon_ids = parse_ids(payload.get("addon_ids", []))

    starts_at = parse_booking_start(str(payload.get("starts_at", "")))
    notes = str(payload.get("notes", "")).strip()
    brand = str(payload.get("brand", "")).strip()
    model = str(payload.get("model", "")).strip()
    registration_number = str(payload.get("registration_number", "")).strip().upper()
    vehicle_size = str(payload.get("vehicle_size", "standard")).strip()
    if vehicle_size not in {"small", "standard", "suv", "van"}:
        vehicle_size = "standard"

    with connect() as conn:
        items = load_selected_booking_items(conn, service_ids, addon_ids)
        services = items["services"]
        addons = items["addons"]
        duration = int(items["duration_minutes"])
        total = float(items["total_price_pln"])
        station_count = validate_booking_window(conn, starts_at, duration)
        ends_at = starts_at + timedelta(minutes=duration)

        if has_booking_conflict(conn, starts_at, ends_at, station_count):
            raise ApiError("Ten termin jest juz zajety. Wybierz inna godzine.")

        customer_id, _, _, _, _ = customer_for_booking(conn, payload, user)
        vehicle = conn.execute(
            """
            INSERT INTO vehicles (
              customer_id, registration_number, brand, model, vehicle_size, color
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                customer_id,
                registration_number,
                brand,
                model,
                vehicle_size,
                str(payload.get("color", "")).strip(),
            ),
        )
        vehicle_id = vehicle.lastrowid

        booking = conn.execute(
            """
            INSERT INTO bookings (
              customer_id, vehicle_id, starts_at, ends_at, status,
              total_price_pln, customer_notes
            )
            VALUES (?, ?, ?, ?, 'new', ?, ?)
            """,
            (
                customer_id,
                vehicle_id,
                starts_at.strftime("%Y-%m-%d %H:%M:%S"),
                ends_at.strftime("%Y-%m-%d %H:%M:%S"),
                round(total, 2),
                notes,
            ),
        )
        booking_id = booking.lastrowid

        conn.executemany(
            """
            INSERT INTO booking_services (booking_id, service_id, price_pln)
            VALUES (?, ?, ?)
            """,
            [(booking_id, row["id"], row["base_price_pln"]) for row in services],
        )
        if addons:
            conn.executemany(
                """
                INSERT INTO booking_addons (booking_id, addon_id, price_pln)
                VALUES (?, ?, ?)
                """,
                [(booking_id, row["id"], row["price_pln"]) for row in addons],
            )
        service_names = ", ".join(row["name"] for row in services) or "wybrana usluga"
        create_client_notification(
            conn,
            customer_id,
            booking_id,
            "booking_created",
            "Rezerwacja przyjeta",
            (
                f"Przyjelismy Twoja rezerwacje na {starts_at.strftime('%Y-%m-%d %H:%M')}. "
                f"Usluga: {service_names}. Kwota: {round(total, 2):.2f} zl."
            ),
        )
        conn.commit()

        return {
            "id": booking_id,
            "starts_at": starts_at.strftime("%Y-%m-%d %H:%M:%S"),
            "ends_at": ends_at.strftime("%Y-%m-%d %H:%M:%S"),
            "total_price_pln": round(total, 2),
        }


def create_contact_message(payload: dict) -> dict:
    name = str(payload.get("name", "")).strip()
    email = str(payload.get("email", "")).strip().lower()
    phone = str(payload.get("phone", "")).strip()
    subject = str(payload.get("subject", "")).strip() or "Wiadomosc ze strony"
    message = str(payload.get("message", "")).strip()

    if not name or "@" not in email or not message:
        raise ApiError("Uzupelnij dane kontaktowe i tresc wiadomosci.")

    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO contact_messages (name, email, phone, subject, message)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, email, phone, subject, message),
        )
        conn.commit()
        return {"id": cursor.lastrowid}


def update_booking_status(payload: dict, user: dict | None) -> dict:
    require_owner(user)
    try:
        booking_id = int(payload.get("booking_id"))
    except (TypeError, ValueError) as exc:
        raise ApiError("Nieprawidlowy numer wizyty.") from exc

    status = str(payload.get("status", "")).strip()
    if status not in BOOKING_STATUSES:
        raise ApiError("Nieprawidlowy status wizyty.")

    with connect() as conn:
        booking = conn.execute(
            """
            SELECT id, customer_id, status, starts_at
            FROM bookings
            WHERE id = ?
            """,
            (booking_id,),
        ).fetchone()
        if booking is None:
            raise ApiError("Nie znaleziono wizyty.", 404)

        cursor = conn.execute(
            """
            UPDATE bookings
            SET status = ?
            WHERE id = ?
            """,
            (status, booking_id),
        )
        if cursor.rowcount == 0:
            raise ApiError("Nie znaleziono wizyty.", 404)
        if booking["status"] != status:
            label = STATUS_NOTIFICATION_LABELS.get(status, status)
            create_client_notification(
                conn,
                booking["customer_id"],
                booking_id,
                "booking_status",
                "Status wizyty zmieniony",
                (
                    f"Status Twojej wizyty z {booking['starts_at'][:16]} "
                    f"zostal zmieniony na: {label}."
                ),
            )
        conn.commit()
        return {"id": booking_id, "status": status}


def update_pricing_item(payload: dict, user: dict | None) -> dict:
    require_owner(user)
    item_type = str(payload.get("type", "")).strip()
    if item_type not in {"service", "addon"}:
        raise ApiError("Nieprawidlowy typ pozycji cennika.")

    try:
        item_id = int(payload.get("id"))
        duration = int(payload.get("duration_minutes"))
        price = float(payload.get("price_pln"))
    except (TypeError, ValueError) as exc:
        raise ApiError("Cena i czas musza byc poprawnymi liczbami.") from exc

    name = str(payload.get("name", "")).strip()
    description = str(payload.get("description", "")).strip()
    if not name:
        raise ApiError("Podaj nazwe pozycji cennika.")
    if not description:
        raise ApiError("Podaj opis pozycji cennika.")
    if duration < 0 or price < 0:
        raise ApiError("Cena i czas nie moga byc ujemne.")
    if item_type == "service" and duration == 0:
        raise ApiError("Usluga musi miec czas trwania.")

    with connect() as conn:
        if item_type == "service":
            cursor = conn.execute(
                """
                UPDATE services
                SET name = ?, description = ?, duration_minutes = ?, base_price_pln = ?
                WHERE id = ?
                """,
                (name, description, duration, price, item_id),
            )
        else:
            cursor = conn.execute(
                """
                UPDATE service_addons
                SET name = ?, description = ?, duration_minutes = ?, price_pln = ?
                WHERE id = ?
                """,
                (name, description, duration, price, item_id),
            )
        if cursor.rowcount == 0:
            raise ApiError("Nie znaleziono pozycji cennika.", 404)
        conn.commit()
        return {"id": item_id, "type": item_type}


def update_owner_schedule(payload: dict, user: dict | None) -> dict:
    require_owner(user)
    try:
        station_count = int(payload.get("station_count"))
    except (TypeError, ValueError) as exc:
        raise ApiError("Podaj liczbe stanowisk.") from exc
    if station_count < 1 or station_count > MAX_STATION_COUNT:
        raise ApiError(f"Liczba stanowisk musi byc od 1 do {MAX_STATION_COUNT}.")

    rows = payload.get("hours", [])
    if not isinstance(rows, list) or len(rows) != 7:
        raise ApiError("Uzupelnij godziny pracy dla wszystkich dni.")

    normalized_rows = []
    seen_weekdays: set[int] = set()
    for row in rows:
        try:
            weekday = int(row.get("weekday"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ApiError("Nieprawidlowy dzien tygodnia.") from exc
        if weekday < 0 or weekday > 6 or weekday in seen_weekdays:
            raise ApiError("Nieprawidlowy dzien tygodnia.")
        seen_weekdays.add(weekday)

        is_open = 1 if row.get("is_open") else 0
        opens_at = normalize_time_value(row.get("opens_at"))
        closes_at = normalize_time_value(row.get("closes_at"))
        if is_open:
            open_time = datetime.strptime(opens_at, "%H:%M")
            close_time = datetime.strptime(closes_at, "%H:%M")
            if close_time <= open_time:
                raise ApiError("Godzina zamkniecia musi byc pozniej niz otwarcia.")
            if (close_time - open_time) < timedelta(minutes=SLOT_INTERVAL_MINUTES):
                raise ApiError("Dzien pracy musi miec przynajmniej jeden slot.")
        normalized_rows.append((weekday, is_open, opens_at, closes_at))

    with connect() as conn:
        conn.executemany(
            """
            INSERT INTO business_hours (weekday, is_open, opens_at, closes_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(weekday) DO UPDATE SET
              is_open = excluded.is_open,
              opens_at = excluded.opens_at,
              closes_at = excluded.closes_at,
              updated_at = CURRENT_TIMESTAMP
            """,
            normalized_rows,
        )
        conn.execute(
            """
            INSERT INTO site_settings (key, value)
            VALUES ('station_count', ?)
            ON CONFLICT(key) DO UPDATE SET
              value = excluded.value,
              updated_at = CURRENT_TIMESTAMP
            """,
            (str(station_count),),
        )
        conn.commit()
        return {"owner_schedule": load_owner_schedule(conn)}


def add_business_closure(payload: dict, user: dict | None) -> dict:
    require_owner(user)
    day = parse_booking_date(str(payload.get("date", ""))).strftime("%Y-%m-%d")
    reason = str(payload.get("reason", "")).strip()[:120]
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO business_closures (date, reason)
            VALUES (?, ?)
            ON CONFLICT(date) DO UPDATE SET
              reason = excluded.reason
            """,
            (day, reason),
        )
        conn.commit()
        return {"owner_schedule": load_owner_schedule(conn)}


def delete_business_closure(payload: dict, user: dict | None) -> dict:
    require_owner(user)
    try:
        closure_id = int(payload.get("id"))
    except (TypeError, ValueError) as exc:
        raise ApiError("Nieprawidlowy dzien wolny.") from exc

    with connect() as conn:
        cursor = conn.execute(
            "DELETE FROM business_closures WHERE id = ?",
            (closure_id,),
        )
        if cursor.rowcount == 0:
            raise ApiError("Nie znaleziono dnia wolnego.", 404)
        conn.commit()
        return {"owner_schedule": load_owner_schedule(conn)}


def update_client_profile(payload: dict, user: dict | None) -> dict:
    require_client(user)
    full_name = str(payload.get("name", "")).strip()
    phone = str(payload.get("phone", "")).strip()
    marketing_consent = 1 if payload.get("marketing_consent") else 0
    if not full_name:
        raise ApiError("Podaj imie i nazwisko.")
    if len(phone) < 7:
        raise ApiError("Podaj numer telefonu.")

    first_name, last_name = split_name(full_name)
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO customers (first_name, last_name, email, phone, marketing_consent)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
              first_name = excluded.first_name,
              last_name = excluded.last_name,
              phone = excluded.phone,
              marketing_consent = excluded.marketing_consent
            """,
            (first_name, last_name, user["email"], phone, marketing_consent),
        )
        customer_id = conn.execute(
            "SELECT id FROM customers WHERE email = ?",
            (user["email"],),
        ).fetchone()["id"]
        conn.execute(
            """
            UPDATE app_users
            SET name = ?, phone = ?, customer_id = ?
            WHERE id = ?
            """,
            (full_name, phone, customer_id, user["id"]),
        )
        conn.commit()
        updated_user = serialize_user(load_user_by_id(conn, user["id"]))
        return {
            "current_user": updated_user,
            "client_profile": load_client_profile(conn, updated_user),
            "client_vehicles": load_client_vehicles(conn, customer_id),
            "my_bookings": load_bookings(conn, customer_id, include_history=True),
        }


def save_client_vehicle(payload: dict, user: dict | None) -> dict:
    require_client(user)
    if not user.get("customer_id"):
        raise ApiError("Najpierw uzupelnij profil klienta.")

    vehicle_size = str(payload.get("vehicle_size", "standard")).strip()
    if vehicle_size not in {"small", "standard", "suv", "van"}:
        raise ApiError("Nieprawidlowy rozmiar auta.")

    registration_number = str(payload.get("registration_number", "")).strip().upper()
    brand = str(payload.get("brand", "")).strip()
    model = str(payload.get("model", "")).strip()
    color = str(payload.get("color", "")).strip()
    if not brand and not model and not registration_number:
        raise ApiError("Podaj przynajmniej marke, model albo rejestracje auta.")

    vehicle_id_raw = payload.get("id")
    with connect() as conn:
        if vehicle_id_raw:
            try:
                vehicle_id = int(vehicle_id_raw)
            except (TypeError, ValueError) as exc:
                raise ApiError("Nieprawidlowe auto.") from exc
            cursor = conn.execute(
                """
                UPDATE vehicles
                SET registration_number = ?, brand = ?, model = ?, vehicle_size = ?, color = ?
                WHERE id = ? AND customer_id = ?
                """,
                (
                    registration_number,
                    brand,
                    model,
                    vehicle_size,
                    color,
                    vehicle_id,
                    user["customer_id"],
                ),
            )
            if cursor.rowcount == 0:
                raise ApiError("Nie znaleziono auta.", 404)
        else:
            conn.execute(
                """
                INSERT INTO vehicles (
                  customer_id, registration_number, brand, model, vehicle_size, color
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user["customer_id"],
                    registration_number,
                    brand,
                    model,
                    vehicle_size,
                    color,
                ),
            )
        conn.commit()
        return {
            "client_vehicles": load_client_vehicles(conn, user["customer_id"]),
            "my_bookings": load_bookings(conn, user["customer_id"], include_history=True),
        }


def cancel_client_booking(payload: dict, user: dict | None) -> dict:
    require_client(user)
    if not user.get("customer_id"):
        raise ApiError("Brak profilu klienta.", 403)
    try:
        booking_id = int(payload.get("booking_id"))
    except (TypeError, ValueError) as exc:
        raise ApiError("Nieprawidlowy numer wizyty.") from exc

    with connect() as conn:
        booking = conn.execute(
            """
            SELECT id, status, starts_at
            FROM bookings
            WHERE id = ? AND customer_id = ?
            """,
            (booking_id, user["customer_id"]),
        ).fetchone()
        if booking is None:
            raise ApiError("Nie znaleziono wizyty.", 404)
        if booking["status"] not in {"new", "confirmed"}:
            raise ApiError("Tej wizyty nie mozna juz odwolac.")
        if datetime.strptime(booking["starts_at"], "%Y-%m-%d %H:%M:%S") <= datetime.now():
            raise ApiError("Nie mozna odwolac wizyty po terminie.")

        conn.execute(
            """
            UPDATE bookings
            SET status = 'cancelled'
            WHERE id = ? AND customer_id = ?
            """,
            (booking_id, user["customer_id"]),
        )
        create_client_notification(
            conn,
            user["customer_id"],
            booking_id,
            "booking_cancelled",
            "Wizyta odwolana",
            f"Twoja wizyta z {booking['starts_at'][:16]} zostala odwolana.",
        )
        conn.commit()
        return {
            "booking": {"id": booking_id, "status": "cancelled"},
            "my_bookings": load_bookings(conn, user["customer_id"], include_history=True),
            "client_notifications": load_client_notifications(conn, user["customer_id"]),
        }


def mark_client_notifications_read(payload: dict, user: dict | None) -> dict:
    require_client(user)
    if not user.get("customer_id"):
        raise ApiError("Brak profilu klienta.", 403)

    notification_id = payload.get("notification_id")
    with connect() as conn:
        if notification_id:
            try:
                parsed_id = int(notification_id)
            except (TypeError, ValueError) as exc:
                raise ApiError("Nieprawidlowe powiadomienie.") from exc
            conn.execute(
                """
                UPDATE client_notifications
                SET is_read = 1, read_at = CURRENT_TIMESTAMP
                WHERE id = ? AND customer_id = ?
                """,
                (parsed_id, user["customer_id"]),
            )
        else:
            conn.execute(
                """
                UPDATE client_notifications
                SET is_read = 1, read_at = CURRENT_TIMESTAMP
                WHERE customer_id = ? AND is_read = 0
                """,
                (user["customer_id"],),
            )
        conn.commit()
        return {"client_notifications": load_client_notifications(conn, user["customer_id"])}


class AppHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        user = current_user(self)

        try:
            if path == "/api/bootstrap":
                self.send_json(bootstrap_payload(user))
                return
            if path == "/api/auth/me":
                self.send_json({"current_user": user})
                return
            if path == "/api/availability":
                day = query.get("date", [datetime.now().strftime("%Y-%m-%d")])[0]
                with connect() as conn:
                    self.send_json(
                        load_availability(
                            conn,
                            day,
                            parse_ids(query.get("service_ids", [])),
                            parse_ids(query.get("addon_ids", [])),
                        )
                    )
                return
            if path == "/api/bookings":
                if not user or user["role"] != "owner":
                    self.send_json({"error": "Dostep tylko dla wlasciciela."}, status=403)
                    return
                with connect() as conn:
                    self.send_json({"bookings": load_bookings(conn), "dashboard": load_dashboard(conn)})
                return
            if path == "/api/owner/day-plan":
                require_owner(user)
                day = query.get("date", [datetime.now().strftime("%Y-%m-%d")])[0]
                with connect() as conn:
                    self.send_json({"bookings": load_bookings(conn, include_history=True, date_value=day)})
                return
            if path == "/api/owner/schedule":
                require_owner(user)
                with connect() as conn:
                    self.send_json({"owner_schedule": load_owner_schedule(conn)})
                return
            if path == "/api/my-bookings":
                if not user or user["role"] != "client":
                    self.send_json({"error": "Dostep tylko dla klienta."}, status=403)
                    return
                with connect() as conn:
                    bookings = load_bookings(conn, user["customer_id"], include_history=True) if user["customer_id"] else []
                    self.send_json({"bookings": bookings})
                return
            if path == "/api/client/notifications":
                require_client(user)
                with connect() as conn:
                    self.send_json(
                        {
                            "client_notifications": load_client_notifications(
                                conn,
                                user["customer_id"],
                            )
                        }
                    )
                return
        except ApiError as exc:
            self.send_json({"error": exc.message}, status=exc.status)
            return
        except sqlite3.Error:
            self.send_json({"error": "Baza danych chwilowo nie odpowiada."}, status=500)
            return
        self.serve_static(path)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = parse_json_body(self)
            if path == "/api/auth/login":
                user = login_user(payload)
                token = create_session(user["id"])
                self.send_json(
                    {"current_user": user},
                    headers=[("Set-Cookie", session_cookie(token))],
                )
                return
            if path == "/api/auth/register":
                user = register_client(payload)
                token = create_session(user["id"])
                self.send_json(
                    {"current_user": user},
                    status=201,
                    headers=[("Set-Cookie", session_cookie(token))],
                )
                return
            if path == "/api/auth/password-reset/request":
                self.send_json(request_password_reset(payload))
                return
            if path == "/api/auth/password-reset/complete":
                self.send_json(complete_password_reset(payload))
                return
            if path == "/api/auth/logout":
                clear_session(self)
                self.send_json(
                    {"ok": True},
                    headers=[("Set-Cookie", expired_session_cookie())],
                )
                return
            if path == "/api/bookings":
                self.send_json({"booking": create_booking(payload, current_user(self))}, status=201)
                return
            if path == "/api/owner/booking-status":
                user = current_user(self)
                result = update_booking_status(payload, user)
                with connect() as conn:
                    self.send_json(
                        {
                            "booking": result,
                            "bookings": load_bookings(conn),
                            "dashboard": load_dashboard(conn),
                        }
                    )
                return
            if path == "/api/owner/pricing":
                update_pricing_item(payload, current_user(self))
                with connect() as conn:
                    self.send_json(
                        {
                            "services": load_services(conn),
                            "addons": load_addons(conn),
                        }
                    )
                return
            if path == "/api/owner/schedule":
                self.send_json(update_owner_schedule(payload, current_user(self)))
                return
            if path == "/api/owner/closure":
                self.send_json(add_business_closure(payload, current_user(self)))
                return
            if path == "/api/owner/delete-closure":
                self.send_json(delete_business_closure(payload, current_user(self)))
                return
            if path == "/api/client/profile":
                self.send_json(update_client_profile(payload, current_user(self)))
                return
            if path == "/api/client/vehicle":
                self.send_json(save_client_vehicle(payload, current_user(self)))
                return
            if path == "/api/client/cancel-booking":
                self.send_json(cancel_client_booking(payload, current_user(self)))
                return
            if path == "/api/client/notifications/read":
                self.send_json(mark_client_notifications_read(payload, current_user(self)))
                return
            if path == "/api/contact":
                self.send_json({"message": create_contact_message(payload)}, status=201)
                return
            self.send_json({"error": "Nie znaleziono endpointu."}, status=404)
        except ApiError as exc:
            self.send_json({"error": exc.message}, status=exc.status)
        except sqlite3.Error:
            self.send_json({"error": "Baza danych chwilowo nie odpowiada."}, status=500)

    def serve_static(self, request_path: str) -> None:
        path = unquote(request_path)
        if path == "/":
            path = "/index.html"

        candidate = (WEB_ROOT / path.lstrip("/")).resolve()
        if WEB_ROOT not in candidate.parents and candidate != WEB_ROOT:
            self.send_error(403)
            return
        if not candidate.exists() or not candidate.is_file():
            candidate = WEB_ROOT / "index.html"

        content_type, _ = mimetypes.guess_type(candidate.name)
        self.send_response(200)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(candidate.read_bytes())

    def send_json(
        self,
        payload: dict,
        status: int = 200,
        headers: list[tuple[str, str]] | None = None,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for key, value in headers or []:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    initialize_database_if_missing()

    ensure_auth_schema()
    ensure_schedule_schema()
    ensure_notification_schema()
    ensure_account_recovery_schema()
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0" if "PORT" in os.environ else "127.0.0.1")
    server = ThreadingHTTPServer((host, port), AppHandler)
    display_host = "127.0.0.1" if host == "0.0.0.0" else host
    print(f"Myjnia AutoClean dziala: http://{display_host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nZatrzymano serwer.")


if __name__ == "__main__":
    main()
