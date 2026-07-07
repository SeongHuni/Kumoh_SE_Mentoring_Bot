from dataclasses import dataclass
from pathlib import Path
import re


FRONT_MATTER_PATTERN = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.DOTALL)


@dataclass(frozen=True)
class KnowledgeDocument:
    id: str
    title: str
    audience: str
    source_urls: list[str]
    last_checked: str
    owner: str
    keywords: list[str]
    body: str
    path: Path


def _parse_scalar(value: str) -> str:
    return value.strip().strip('"').strip("'")


def _parse_front_matter(text: str) -> tuple[dict[str, object], str]:
    match = FRONT_MATTER_PATTERN.match(text)
    if not match:
        raise ValueError("Markdown file must start with YAML-style front matter.")

    raw_meta, body = match.groups()
    meta: dict[str, object] = {}
    current_list_key: str | None = None

    for raw_line in raw_meta.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue

        if line.startswith("  - ") and current_list_key:
            meta.setdefault(current_list_key, [])
            assert isinstance(meta[current_list_key], list)
            meta[current_list_key].append(_parse_scalar(line[4:]))
            continue

        if ":" not in line:
            continue

        key, raw_value = line.split(":", 1)
        key = key.strip()
        value = raw_value.strip()
        current_list_key = None

        if value == "":
            meta[key] = []
            current_list_key = key
        else:
            meta[key] = _parse_scalar(value)

    return meta, body.strip()


def load_markdown_document(path: Path) -> KnowledgeDocument:
    meta, body = _parse_front_matter(path.read_text(encoding="utf-8"))

    required = ["id", "title", "audience", "source_urls", "last_checked", "owner", "keywords"]
    missing = [key for key in required if key not in meta]
    if missing:
        raise ValueError(f"{path} is missing required metadata: {', '.join(missing)}")

    raw_keywords = str(meta["keywords"])
    keywords = [keyword.strip() for keyword in raw_keywords.split(",") if keyword.strip()]

    source_urls = meta["source_urls"]
    if not isinstance(source_urls, list):
        source_urls = [str(source_urls)]

    return KnowledgeDocument(
        id=str(meta["id"]),
        title=str(meta["title"]),
        audience=str(meta["audience"]),
        source_urls=[str(url) for url in source_urls],
        last_checked=str(meta["last_checked"]),
        owner=str(meta["owner"]),
        keywords=keywords,
        body=body,
        path=path,
    )


def load_knowledge_documents(directory: Path) -> list[KnowledgeDocument]:
    if not directory.exists():
        return []

    return [
        load_markdown_document(path)
        for path in sorted(directory.glob("*.md"))
        if path.is_file()
    ]

