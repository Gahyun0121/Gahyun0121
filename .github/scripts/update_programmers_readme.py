import subprocess
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
SOLUTIONS_DIR = ROOT / "프로그래머스"
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


def solved_problem_dirs():
    if not SOLUTIONS_DIR.is_dir():
        return []
    dirs = [p for level_dir in SOLUTIONS_DIR.iterdir() if level_dir.is_dir()
            for p in level_dir.iterdir() if p.is_dir()]
    return dirs


def build_list_items(dirs) -> str:
    if not dirs:
        return "- 아직 푼 문제가 없어요. 프로그래머스에서 문제를 풀면 여기에 표시돼요!"

    dated = [(last_commit_time(d), d) for d in dirs]
    dated.sort(key=lambda item: item[0], reverse=True)

    lines = []
    for _, d in dated[:MAX_COUNT]:
        level = d.parent.name
        title = d.name
        link = quote(str(d.relative_to(ROOT)).replace("\\", "/"))
        lines.append(f"- [{level}] {title} ([바로가기]({link}))")
    return "\n".join(lines)


def update_readme(list_markdown: str) -> None:
    content = README.read_text(encoding="utf-8")
    start = content.index(START_TAG) + len(START_TAG)
    end = content.index(END_TAG)
    new_content = content[:start] + "\n" + list_markdown + "\n" + content[end:]
    README.write_text(new_content, encoding="utf-8")


def main() -> None:
    dirs = solved_problem_dirs()
    list_markdown = build_list_items(dirs)
    update_readme(list_markdown)


if __name__ == "__main__":
    main()
