from pathlib import Path
import sys

import pymysql

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings

settings = get_settings()

if settings.is_postgres:
    print('DATABASE_URL is PostgreSQL. Skipping manual create_database step.')
    raise SystemExit(0)

conn = pymysql.connect(
    host=settings.mysql_host,
    port=settings.mysql_port,
    user=settings.mysql_user,
    password=settings.mysql_password,
    autocommit=True,
)

with conn.cursor() as cur:
    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{settings.mysql_db}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")

print(f"Database '{settings.mysql_db}' is ready.")
