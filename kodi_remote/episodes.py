"""Conservative episode matching within a single local directory."""
import re
from pathlib import Path

VIDEO = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts", ".m2ts", ".webm"}
EXTRA = re.compile(r"(?:^|[\W_])(?:sample|trailer|ncop\d*|nced\d*|op\d*|ed\d*)(?:$|[\W_])", re.I)
PATTERNS = [
    re.compile(r"^(.*?)(?<![a-zA-Z0-9])S(\d{1,2})E(\d{1,3})(?!\d|[Ee]\d)", re.I),
    re.compile(r"^(.*?)第\s*(\d{1,3})\s*[集话話]"),
    re.compile(r"^(.*?)(?:^|[\W_])EP?(\d{1,3})(?!\d)", re.I),
    re.compile(r"^(.*?)\[(\d{1,3})\]"),
    re.compile(r"^(.*?)\s-\s(\d{1,3})(?=$|[\W_])"),
    re.compile(r"^()(\d{1,3})$"),
]


def natural(value):
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", value)]


def playable(path):
    p = Path(path)
    return p.suffix.lower() in VIDEO and not EXTRA.search(p.stem)


def identify(path):
    stem = Path(path).stem
    # Multi-episode packs and ambiguous ranges require manual selection.
    if re.search(r"(?:E\d+[-~]E?\d+|\d+[-~]\d+|E\d+E\d+)", stem, re.I):
        return None
    for index, pattern in enumerate(PATTERNS):
        match = pattern.search(stem)
        if match:
            groups = match.groups()
            prefix = re.sub(r"\[[^]]*\]", "", groups[0])
            series = re.sub(r"[\W_]+", "", prefix).casefold()
            season, episode = (int(groups[1]), int(groups[2])) if index == 0 else (None, int(groups[1]))
            return series, season, episode
    return None


def neighbors(current, files, direction):
    """Return (unique target, candidates, reason); never silently skip missing episodes."""
    candidates = sorted([p for p in files if p != current and playable(p)], key=natural)
    identity = identify(current)
    if identity is None:
        return None, candidates, "无法可靠识别集号，请选择文件"
    series, season, episode = identity
    matching = [p for p in candidates if identify(p) == (series, season, episode + direction)]
    if len(matching) == 1:
        return matching[0], candidates, ""
    if matching:
        return None, matching, "同一集有多个版本，请选择文件"
    # Clear, consistent episode naming: a gap is a missing episode, not a cue to skip.
    compatible = [p for p in candidates if identify(p) and identify(p)[:2] == (series, season)]
    if compatible or not candidates:
        return None, [], "上一集未找到" if direction < 0 else "下一集未找到"
    return None, candidates, "文件命名不一致，请选择文件"
