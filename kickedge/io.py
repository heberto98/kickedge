from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid

import duckdb


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)


def sql_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def records(con, query: str, params=None) -> list[dict]:
    result = con.execute(query, params or [])
    names = [d[0] for d in result.description]
    return [dict(zip(names, row)) for row in result.fetchall()]


def parquet_info(path: Path) -> dict:
    with duckdb.connect() as con:
        schema = records(con, "DESCRIBE SELECT * FROM read_parquet(?)", [str(path)])
        count = con.execute("SELECT count(*) FROM read_parquet(?)", [str(path)]).fetchone()[0]
    return {"row_count": count, "schema": [
        {"name": c["column_name"], "type": c["column_type"]} for c in schema
    ]}


def write_parquet(con, query: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY ({query}) TO {sql_literal(path.as_posix())} (FORMAT PARQUET, COMPRESSION ZSTD)")
