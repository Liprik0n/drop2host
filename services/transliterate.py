import re

_CYR_TO_LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d",
    "е": "e", "ё": "yo", "ж": "zh", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
}


def transliterate(text: str) -> str:
    """Transliterate Cyrillic to Latin and normalize to a valid slug."""
    text = text.lower().strip()
    result = []
    for char in text:
        if char in _CYR_TO_LAT:
            result.append(_CYR_TO_LAT[char])
        elif char.isascii() and (char.isalnum() or char == "-"):
            result.append(char)
        elif char in (" ", "_", "."):
            result.append("-")
        # skip other characters
    slug = "".join(result)
    slug = re.sub(r"-{2,}", "-", slug)
    slug = slug.strip("-")
    return slug


def validate_slug(slug: str, min_len: int = 3, max_len: int = 30) -> str | None:
    """Validate slug. Returns error message or None if valid."""
    if not slug:
        return "Имя не может быть пустым после транслитерации."
    if len(slug) < min_len:
        return f"Слишком короткое имя (минимум {min_len} символа)."
    if len(slug) > max_len:
        return f"Слишком длинное имя (максимум {max_len} символов)."
    if not re.match(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$", slug):
        return "Имя должно начинаться и заканчиваться буквой/цифрой, содержать только латиницу, цифры и дефисы."
    return None
