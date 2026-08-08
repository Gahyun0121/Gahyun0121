"""programmers/ 폴더의 풀이 파일을 읽어 README 의 최근 목록을 갱신합니다.

폴더 구조 예시
    programmers/L0_기초입문/입문/001_두_수의_차_구하기.py
                └ 레벨      └ 분류  └ 번호_문제이름.py
"""

import subprocess
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
SOLUTIONS_DIR = ROOT / "programmers"
START_TAG = "<!-- PROGRAMMERS-LIST:START -->"
END_TAG = "<!-- PROGRAMMERS-LIST:END -->"
MAX_COUNT = 5


def last_commit_time(path: Path) -> int:
    result = subprocess.run(
        ["git", "log", "-1", "--format=%ct", "--", str(path.relative_to(ROOT))],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    output = result.stdout.strip()
    return int(output) if output else 0


def solution_files():
    if not SOLUTIONS_DIR.is_dir():
        return []
    return [p for p in SOLUTIONS_DIR.rglob("*.py") if p.is_file()]


def describe(path: Path) -> tuple[str, str]:
    """파일 경로에서 (레벨, 제목) 을 뽑습니다."""
    level = path.relative_to(SOLUTIONS_DIR).parts[0]  # L0_기초입문
    level = level.split("_", 1)[0]                    # L0

    stem = path.stem                                  # 001_두_수의_차_구하기
    number, _, name = stem.partition("_")
    if not number.isdigit():                          # 번호가 없는 파일명도 허용
        number, name = "", stem

    # 밑줄을 공백으로 바꾸면 "완성조건__1_" 처럼 공백이 겹치므로 한 칸으로 정리합니다
    name = " ".join(name.replace("_", " ").split())
    return level, f"{number}. {name}" if number else name


def build_list_items(files) -> str:
    if not files:
        return "- 아직 푼 문제가 없어요. 프로그래머스에서 문제를 풀면 여기에 표시돼요!"

    dated = [(last_commit_time(f), f) for f in files]
    dated.sort(key=lambda item: item[0], reverse=True)

    lines = []
    for _, f in dated[:MAX_COUNT]:
        level, title = describe(f)
        link = quote(str(f.relative_to(ROOT)).replace("\\", "/"))
        lines.append(f"- [{level}] {title} ([바로가기]({link}))")
    return "\n".join(lines)


def update_readme(list_markdown: str) -> None:
    content = README.read_text(encoding="utf-8")
    start = content.index(START_TAG) + len(START_TAG)
    end = content.index(END_TAG)
    new_content = content[:start] + "\n" + list_markdown + "\n" + content[end:]
    README.write_text(new_content, encoding="utf-8")


def main() -> None:
    files = solution_files()
    print(f"[info] 풀이 파일 {len(files)}개 발견")
    update_readme(build_list_items(files))


if __name__ == "__main__":
    main()
