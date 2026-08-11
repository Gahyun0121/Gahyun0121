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
MAX_TITLE = int(os.environ.get("MAX_TITLE", "40") or 0)
MAX_TAGS = int(os.environ.get("MAX_TAGS", "0") or 0)      # 0 이면 전부 표시
TITLE_STRIP = os.environ.get("TITLE_STRIP", "")            # 제목에서 떼어낼 접두어

# 특정 값인 항목만 표에 넣기 — "속성이름=값" 또는 "속성이름=값1|값2"
FILTER_PROP, _, _values = os.environ.get("TIL_FILTER", "").partition("=")
FILTER_PROP = FILTER_PROP.strip()
FILTER_VALUES = {v.strip() for v in _values.split("|") if v.strip()}

# 표 머리글 바꿔 달기 — "노션속성이름=보여줄이름" 을 콤마로 나열
HEADERS = dict(
    pair.split("=", 1)
    for pair in (p.strip() for p in os.environ.get("TIL_HEADERS", "").split(","))
    if "=" in pair
)


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


def nowrap(text: str) -> str:
    """줄바꿈될 자리를 없앱니다 — 하이픈은 점으로, 공백은 줄바꿈 없는 공백으로."""
    return text.replace("-", ".").replace(" ", "&nbsp;")


def render_table(
    pages: list[dict],
    columns: list[str],
    title_column: str | None,
    types: dict[str, str],
    max_title: int = 0,
    max_tags: int = 0,
) -> str:
    header = "| " + " | ".join(HEADERS.get(c, c) for c in columns) + " |"
    divider = "|" + "|".join("---" for _ in columns) + "|"
    lines = [header, divider]

    for page in pages:
        cells = []
        for name in columns:
            text = plain(page["properties"].get(name, {}))
            kind = types.get(name, "")

            if name == title_column:
                if TITLE_STRIP and text.startswith(TITLE_STRIP):
                    text = text[len(TITLE_STRIP):].lstrip()
                if max_title and len(text) > max_title:
                    text = text[: max_title - 1].rstrip() + "…"
                url = (page.get("url") or "").replace(" ", "%20")
                text = f"[{cell(text)}]({url})"
            elif kind == "multi_select" and max_tags:
                tags = [o.get("name", "") for o in page["properties"][name].get("multi_select") or []]
                shown = ", ".join(tags[:max_tags])
                text = cell(shown + (f" +{len(tags) - max_tags}" if len(tags) > max_tags else ""))
            elif kind in ("date", "created_time", "last_edited_time", "status", "select"):
                # 날짜·상태는 폭이 좁으니 접히지 않게, 제목만 접히도록 둡니다
                text = nowrap(cell(text))
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

    # 무엇이 읽혔는지 그대로 보여줍니다 — 안 올라오는 글을 추적할 때 씁니다
    title_name = title_key(properties)
    print(f"[info] 노션에서 읽은 항목 {len(pages)}건:")
    for page in sorted(pages, key=lambda p: p.get("created_time", ""), reverse=True):
        made = (page.get("created_time") or "")[:10]
        name = plain(page["properties"].get(title_name, {})) if title_name else "?"
        state = plain(page["properties"].get(FILTER_PROP, {})) if FILTER_PROP else ""
        print(f"       생성 {made} | {FILTER_PROP}={state or '(빈칸)'} | {name}")

    if FILTER_PROP and FILTER_VALUES:
        if FILTER_PROP not in properties:
            print(f"[warn] '{FILTER_PROP}' 속성이 없어 필터를 건너뜁니다.")
        else:
            kept = [p for p in pages if plain(p["properties"].get(FILTER_PROP, {})) in FILTER_VALUES]
            print(f"[info] {FILTER_PROP}={'|'.join(sorted(FILTER_VALUES))} 필터 → "
                  f"{len(pages)}건 중 {len(kept)}건 남음")
            pages = kept

    if not pages:
        print("[warn] 필터를 통과한 항목이 없습니다. 문서를 그대로 둡니다.")
        return 0

    columns = pick_columns(properties)
    title_column = title_key(properties)
    types = {name: prop["type"] for name, prop in properties.items()}
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
            render_table(pages, columns, title_column, types),
            "",
        ])
        write_file(Path(TIL_PATH), body)

    if README_PATH:
        recent = pages[:RECENT_COUNT]
        block = "\n".join([
            "",
            render_table(recent, columns, title_column, types, MAX_TITLE, MAX_TAGS),
            "",
            (f"👉 전체 {len(pages)}건 보기 → **[TIL.md]({TIL_PATH})**  ·  " if TIL_PATH else "")
            + f"_마지막 동기화 {stamp}_",
            "",
        ])
        replace_marked_section(Path(README_PATH), block)

    return 0


if __name__ == "__main__":
    sys.exit(main())
