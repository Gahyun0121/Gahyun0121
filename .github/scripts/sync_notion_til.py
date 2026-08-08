#!/usr/bin/env python3
"""노션 TIL 데이터베이스를 읽어 README.md / TIL.md 에 마크다운 표로 렌더링합니다.

표준 라이브러리만 사용합니다(설치할 패키지 없음).

환경 변수
  NOTION_TOKEN        (필수) 노션 통합(integration) 시크릿
  NOTION_DATABASE_ID  (필수) TIL 데이터베이스 ID
  README_PATH         기본 README.md — 마커 구간만 교체. 빈 값이면 건너뜀
  TIL_PATH            기본 TIL.md — 전체 표로 덮어씀. 빈 값이면 건너뜀
  RECENT_COUNT        README 에 넣을 최근 항목 수 (기본 10)
  TIL_COLUMNS         쓸 속성 이름을 콤마로 지정 (미지정 시 자동 감지)
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

API = "https://api.notion.com/v1"
NEW_VERSION = "2026-03-11"   # 데이터베이스 = 데이터 소스 분리 이후
LEGACY_VERSION = "2022-06-28"  # 단일 데이터 소스 DB 폴백용
KST = timezone(timedelta(hours=9))

MARKER_TAG = os.environ.get("MARKER_TAG", "NOTION-TIL")
START_MARKER = f"<!-- {MARKER_TAG}:START -->"
END_MARKER = f"<!-- {MARKER_TAG}:END -->"

TOKEN = os.environ.get("NOTION_TOKEN", "").strip()
DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "").strip()
README_PATH = os.environ.get("README_PATH", "README.md").strip()
TIL_PATH = os.environ.get("TIL_PATH", "TIL.md").strip()
RECENT_COUNT = int(os.environ.get("RECENT_COUNT", "10") or 10)
COLUMN_OVERRIDE = [c.strip() for c in os.environ.get("TIL_COLUMNS", "").split(",") if c.strip()]


# ---------------------------------------------------------------- 노션 API

def _request(method: str, path: str, version: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{API}{path}", data=data, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Notion-Version", version)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"{method} {path} → HTTP {exc.code}\n{exc.read().decode(errors='replace')}"
        ) from None


def _query_all(path: str, version: str) -> list[dict]:
    pages, cursor = [], None
    while True:
        body: dict = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        payload = _request("POST", path, version, body)
        pages.extend(payload.get("results", []))
        if not payload.get("has_more"):
            return pages
        cursor = payload["next_cursor"]


def fetch_pages(database_id: str) -> list[dict]:
    """신 API(데이터 소스) 우선, 안 되면 구 버전 엔드포인트로 폴백."""
    sources = []
    try:
        database = _request("GET", f"/databases/{database_id}", NEW_VERSION)
        sources = database.get("data_sources") or []
    except RuntimeError as err:
        print(f"[info] {NEW_VERSION} 조회 실패 → {LEGACY_VERSION} 으로 재시도합니다.\n{err}")

    if sources:
        source = sources[0]
        print(f"[info] data source: {source.get('name') or source['id']}")
        return _query_all(f"/data_sources/{source['id']}/query", NEW_VERSION)
    return _query_all(f"/databases/{database_id}/query", LEGACY_VERSION)


# ------------------------------------------------------------ 속성 → 텍스트

def plain(prop: dict) -> str:
    kind = prop.get("type")
    value = prop.get(kind)

    if kind in ("title", "rich_text"):
        return "".join(part.get("plain_text", "") for part in value or [])
    if kind == "date":
        if not value:
            return ""
        start, end = value.get("start", "") or "", value.get("end") or ""
        return f"{start[:10]} ~ {end[:10]}" if end else start[:10]
    if kind in ("select", "status"):
        return value.get("name", "") if value else ""
    if kind == "multi_select":
        return ", ".join(option.get("name", "") for option in value or [])
    if kind == "people":
        return ", ".join(person.get("name", "") for person in value or [])
    if kind == "files":
        return ", ".join(f.get("name", "") for f in value or [])
    if kind in ("checkbox", "boolean"):
        return "✅" if value else ""
    if kind == "number":
        return "" if value is None else str(value)
    if kind in ("url", "email", "phone_number"):
        return value or ""
    if kind in ("created_time", "last_edited_time"):
        return (value or "")[:10]
    if kind == "formula":
        return plain({"type": value.get("type"), value.get("type"): value.get(value.get("type"))}) if value else ""
    if kind == "rollup":
        if not value:
            return ""
        if value.get("type") == "array":
            return ", ".join(filter(None, (plain(item) for item in value.get("array") or [])))
        return plain({"type": value.get("type"), value.get("type"): value.get(value.get("type"))})
    if kind == "unique_id":
        prefix = (value or {}).get("prefix") or ""
        return f"{prefix}{(value or {}).get('number', '')}"
    if kind == "string":  # formula 내부용
        return value or ""
    return ""


def title_key(properties: dict) -> str | None:
    for name, prop in properties.items():
        if prop.get("type") == "title":
            return name
    return None


def pick_columns(properties: dict) -> list[str]:
    """표에 쓸 속성 이름을 고릅니다. 제목 + 날짜 + 태그 + 상태 순."""
    if COLUMN_OVERRIDE:
        missing = [c for c in COLUMN_OVERRIDE if c not in properties]
        if missing:
            print(f"[warn] TIL_COLUMNS 에 없는 속성: {missing}")
        return [c for c in COLUMN_OVERRIDE if c in properties]

    columns: list[str] = []
    title = title_key(properties)
    if title:
        columns.append(title)

    def first_of(*types: str) -> str | None:
        for name, prop in properties.items():
            if name not in columns and prop.get("type") in types:
                return name
        return None

    for candidate in (
        first_of("date"),
        first_of("multi_select"),
        first_of("status", "select"),
    ):
        if candidate:
            columns.append(candidate)
    return columns


# --------------------------------------------------------------- 표 만들기

def cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip() or "—"


def sort_key(page: dict, date_column: str | None) -> str:
    if date_column:
        value = plain(page["properties"].get(date_column, {}))
        if value:
            return value
    return page.get("created_time", "")


def render_table(pages: list[dict], columns: list[str], title_column: str | None) -> str:
    header = "| " + " | ".join(columns) + " |"
    divider = "|" + "|".join("---" for _ in columns) + "|"
    lines = [header, divider]

    for page in pages:
        cells = []
        for name in columns:
            text = plain(page["properties"].get(name, {}))
            if name == title_column:
                url = (page.get("url") or "").replace(" ", "%20")
                text = f"[{cell(text)}]({url})"
            else:
                text = cell(text)
            cells.append(text)
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def replace_marked_section(path: Path, block: str) -> bool:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    payload = f"{START_MARKER}\n{block}\n{END_MARKER}"

    if START_MARKER in text and END_MARKER in text:
        head, rest = text.split(START_MARKER, 1)
        _, tail = rest.split(END_MARKER, 1)
        updated = head + payload + tail
    else:
        print(f"[info] {path} 에 마커가 없어 문서 끝에 새로 추가합니다.")
        updated = (text.rstrip() + "\n\n" if text.strip() else "") + payload + "\n"

    if updated == text:
        print(f"[ok] {path} 변경 없음")
        return False
    path.write_text(updated, encoding="utf-8")
    print(f"[ok] {path} 갱신")
    return True


def write_file(path: Path, content: str) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") == content:
        print(f"[ok] {path} 변경 없음")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"[ok] {path} 갱신")
    return True


# -------------------------------------------------------------------- main

def main() -> int:
    if not TOKEN or not DATABASE_ID:
        print("[error] NOTION_TOKEN 과 NOTION_DATABASE_ID 가 필요합니다.", file=sys.stderr)
        return 1

    pages = [p for p in fetch_pages(DATABASE_ID) if not p.get("archived") and not p.get("in_trash")]
    if not pages:
        print("[warn] 가져온 항목이 0건입니다. 통합이 데이터베이스에 연결됐는지 확인하세요.")
        return 0

    properties = pages[0]["properties"]
    print("[info] 감지된 속성: " + ", ".join(f"{n}({p['type']})" for n, p in properties.items()))

    columns = pick_columns(properties)
    title_column = title_key(properties)
    date_column = next((c for c in columns if properties[c]["type"] == "date"), None)
    print(f"[info] 표 컬럼: {columns}")

    pages.sort(key=lambda p: sort_key(p, date_column), reverse=True)
    stamp = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")

    if TIL_PATH:
        body = "\n".join([
            "# TIL",
            "",
            f"노션 TIL 데이터베이스에서 자동 생성됩니다. 총 **{len(pages)}건** · 최근 동기화 {stamp}",
            "",
            render_table(pages, columns, title_column),
            "",
        ])
        write_file(Path(TIL_PATH), body)

    if README_PATH:
        recent = pages[:RECENT_COUNT]
        block = "\n".join([
            "",
            render_table(recent, columns, title_column),
            "",
            (f"👉 전체 {len(pages)}건 보기 → **[TIL.md]({TIL_PATH})**  ·  " if TIL_PATH else "")
            + f"_마지막 동기화 {stamp}_",
            "",
        ])
        replace_marked_section(Path(README_PATH), block)

    return 0


if __name__ == "__main__":
    sys.exit(main())
