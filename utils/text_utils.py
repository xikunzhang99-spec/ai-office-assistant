import re


def extract_tags(text: str) -> list[str]:
    tags = re.findall(r"#(\w+)", text)
    return list(set(tags))


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def truncate(text: str, max_len: int = 200) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def safe_filename(name: str) -> str:
    return re.sub(r"[^\w\-_\.]", "_", name)
