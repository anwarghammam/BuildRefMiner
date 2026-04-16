import os
import re


LINE_COMMENT_RE = re.compile(r"//.*?$", re.MULTILINE)
BLOCK_COMMENT_RE = re.compile(r"/\*([\s\S]*?)\*/")
XML_COMMENT_RE = re.compile(r"<!--([\s\S]*?)-->")
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
SENTENCE_SPLIT_RE = re.compile(r"[.!?]+")
WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")


def _detect_comment_mode(file_path: str) -> str:
    name = os.path.basename(file_path).lower()
    if name.endswith((".gradle", ".gradle.kts", ".groovy")):
        return "gradle"
    if name in {"pom.xml", "build.xml"} or name.endswith(".xml"):
        return "xml"
    return "unknown"


def _extract_gradle_comments(text: str) -> list[str]:
    comments: list[str] = []
    comments.extend(match.group(0)[2:].strip() for match in LINE_COMMENT_RE.finditer(text))
    comments.extend(match.group(1).strip() for match in BLOCK_COMMENT_RE.finditer(text))
    return [comment for comment in comments if comment]


def _extract_xml_comments(text: str) -> list[str]:
    return [match.group(1).strip() for match in XML_COMMENT_RE.finditer(text) if match.group(1).strip()]


def extract_comments(file_path: str) -> str:
    if not file_path or not os.path.exists(file_path):
        return ""

    with open(file_path, "r", encoding="utf-8", errors="replace") as handle:
        raw = handle.read()

    mode = _detect_comment_mode(file_path)
    if mode == "gradle":
        comments = _extract_gradle_comments(raw)
    elif mode == "xml":
        comments = _extract_xml_comments(raw)
    else:
        comments = []

    return "\n".join(comments)


def _normalize_comment_text(text: str) -> str:
    text = URL_RE.sub(" ", text)
    text = re.sub(r"\$\{[^}]+\}", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"`[^`]+`", " ", text)
    text = re.sub(r"[_/\\\\|=*#~^]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _count_syllables(word: str) -> int:
    word = re.sub(r"[^a-z]", "", word.lower())
    if not word:
        return 0

    vowels = "aeiouy"
    count = 0
    prev_is_vowel = False

    for ch in word:
        is_vowel = ch in vowels
        if is_vowel and not prev_is_vowel:
            count += 1
        prev_is_vowel = is_vowel

    if word.endswith("e") and count > 1:
        count -= 1
    if word.endswith("le") and len(word) > 2 and word[-3] not in vowels:
        count += 1

    return max(1, count)


def compute_comment_readability_stats(file_path: str) -> dict[str, float | int]:
    text = _normalize_comment_text(extract_comments(file_path))
    if not text:
        return {
            "comment_text": "",
            "sentence_count": 0,
            "word_count": 0,
            "syllable_count": 0,
            "flesch_reading_ease": 0.0,
        }

    sentence_candidates = [segment.strip() for segment in SENTENCE_SPLIT_RE.split(text) if segment.strip()]
    words = WORD_RE.findall(text)
    syllables = sum(_count_syllables(word) for word in words)
    sentence_count = max(1, len(sentence_candidates))
    word_count = len(words)

    if word_count < 3:
        score = 0.0
    else:
        score = 206.835 - 1.015 * (word_count / sentence_count) - 84.6 * (syllables / word_count)
        score = round(score, 2)

    return {
        "comment_text": text,
        "sentence_count": sentence_count if word_count else 0,
        "word_count": word_count,
        "syllable_count": syllables,
        "flesch_reading_ease": score,
    }


def compute_comment_readability(file_path: str) -> float:
    return float(compute_comment_readability_stats(file_path)["flesch_reading_ease"])
