"""
The evaluation checklist for a short tutorial.

Twelve items, split by WHO can check them reliably:

  R1-R8  `rule`  — checked by plain Python (no LLM, fully deterministic,
                   re-runnable on the final text).
  L1-L4  `llm`   — qualitative, checked by the Reviewer agent (LLM).

Mixing both is deliberate: an LLM is a poor counter of words/steps and a
regex is a poor judge of "one action per step", so each kind of item goes
to the checker that is good at it.

Why R5-R8 exist: a small LLM reviewing its own kind of output rubber-stamps
defects (a title with a wrong word, a missing `git init`, an API key hard-coded
right after telling the reader to use an environment variable, a version check
before the install step). Everything that CAN be decided from the text alone is
therefore decided by code, so it no longer depends on the model noticing it.
"""
from __future__ import annotations

import re
import unicodedata
from bisect import bisect_right
from dataclasses import dataclass

from app.schemas import ChecklistItem, ItemResult
from app.textutil import find_invisible_chars

# --- Checklist definition ------------------------------------------------------

CHECKLIST: list[ChecklistItem] = [
    ChecklistItem(
        id="R1",
        kind="rule",
        description="Có tiêu đề cấp 1 (dòng bắt đầu bằng '# ').",
    ),
    ChecklistItem(
        id="R2",
        kind="rule",
        description=(
            "Có đủ 5 mục (heading '##'): Mục tiêu, Chuẩn bị, Các bước, "
            "Kiểm tra kết quả, Lỗi thường gặp."
        ),
    ),
    ChecklistItem(
        id="R3",
        kind="rule",
        description="Mục 'Các bước' là danh sách đánh số gồm từ 3 đến 8 bước.",
    ),
    ChecklistItem(
        id="R4",
        kind="rule",
        description="Độ dài không vượt quá giới hạn từ (không tính khối code).",
    ),
    ChecklistItem(
        id="R5",
        kind="rule",
        description=(
            "Tiêu đề dùng đúng thuật ngữ của chủ đề: không có từ lạ không xuất hiện "
            "trong chủ đề hay trong nội dung bài."
        ),
    ),
    ChecklistItem(
        id="R6",
        kind="rule",
        description="Không có ký tự ẩn hoặc khoảng trắng đặc biệt (zero-width space, NBSP, ký tự điều khiển).",
    ),
    ChecklistItem(
        id="R7",
        kind="rule",
        description=(
            "Trình tự lệnh hợp lý: lệnh phụ thuộc chỉ xuất hiện sau lệnh tiền đề "
            "(vd. git push sau git init + git commit; kích hoạt venv sau khi tạo venv; "
            "không kiểm tra phiên bản công cụ trước bước cài đặt công cụ đó)."
        ),
    ),
    ChecklistItem(
        id="R8",
        kind="rule",
        description="Mã không gán cứng khóa API/token/mật khẩu; khóa phải đọc từ biến môi trường.",
    ),
    ChecklistItem(
        id="L1",
        kind="llm",
        description="Mỗi bước chỉ yêu cầu MỘT hành động rõ ràng, viết ở thể mệnh lệnh.",
    ),
    ChecklistItem(
        id="L2",
        kind="llm",
        description="Mọi lệnh/đoạn mã/giá trị cụ thể được đặt trong định dạng code (khối code hoặc code inline), không mơ hồ.",
    ),
    ChecklistItem(
        id="L3",
        kind="llm",
        description="Ngôn ngữ phù hợp đối tượng người đọc; thuật ngữ khó được giải thích ở lần đầu xuất hiện.",
    ),
    ChecklistItem(
        id="L4",
        kind="llm",
        description="Nội dung bám sát chủ đề, ngắn gọn, không lan man hay thông tin thừa.",
    ),
]

RULE_ITEMS: list[ChecklistItem] = [c for c in CHECKLIST if c.kind == "rule"]
LLM_ITEMS: list[ChecklistItem] = [c for c in CHECKLIST if c.kind == "llm"]

# Required sections: label shown to the user -> keywords, any of which in a
# '##' heading counts as that section being present (case-insensitive).
REQUIRED_SECTIONS: dict[str, tuple[str, ...]] = {
    "Mục tiêu": ("mục tiêu",),
    "Chuẩn bị": ("chuẩn bị",),
    "Các bước": ("các bước", "thực hiện"),
    "Kiểm tra kết quả": ("kiểm tra", "kết quả"),
    "Lỗi thường gặp": ("lỗi", "sự cố"),
}
MIN_STEPS, MAX_STEPS = 3, 8

_H1_RE = re.compile(r"^# \S", re.MULTILINE)
_H1_LINE_RE = re.compile(r"^# (\S.*?)\s*$", re.MULTILINE)
_H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_STEP_RE = re.compile(r"^\s*\d+[.)]\s+\S", re.MULTILINE)
_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)


# --- Helpers ---------------------------------------------------------------------


def strip_code_blocks(text: str) -> str:
    """Remove fenced code blocks (``` ... ```)."""
    return _CODE_FENCE_RE.sub(" ", text)


def count_words(text: str) -> int:
    """Count whitespace-separated words, ignoring fenced code blocks."""
    return len(strip_code_blocks(text).split())


def _headings(text: str) -> list[str]:
    return [m.group(1) for m in _H2_RE.finditer(strip_code_blocks(text))]


def _section_body(text: str, keywords: tuple[str, ...]) -> str | None:
    """Return the body of the first '##' section whose heading has one of `keywords`."""
    clean = strip_code_blocks(text)
    matches = list(_H2_RE.finditer(clean))
    for i, m in enumerate(matches):
        if any(k in m.group(1).lower() for k in keywords):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(clean)
            return clean[m.end():end]
    return None


def _mask_code_blocks(text: str) -> str:
    """Blank out fenced code (keeping newlines and length) so positions still line up with `text`."""
    return _CODE_FENCE_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group()), text)


def _raw_section(text: str, keywords: tuple[str, ...]) -> str:
    """Like `_section_body` but KEEPS code blocks. Returns '' if the section is missing."""
    masked = _mask_code_blocks(text)
    matches = list(_H2_RE.finditer(masked))
    for i, m in enumerate(matches):
        if any(k in m.group(1).lower() for k in keywords):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            return text[m.end():end]
    return ""


def _words(text: str) -> list[str]:
    return [w.lower() for w in _WORD_RE.findall(unicodedata.normalize("NFC", text))]


# --- R1-R4 -----------------------------------------------------------------------


def check_title(text: str) -> tuple[bool, str]:
    ok = bool(_H1_RE.search(strip_code_blocks(text)))
    return ok, "Có tiêu đề." if ok else "Thiếu tiêu đề cấp 1 ('# Tên bài hướng dẫn')."


def check_sections(text: str) -> tuple[bool, str]:
    headings = [h.lower() for h in _headings(text)]
    missing = [
        label
        for label, kws in REQUIRED_SECTIONS.items()
        if not any(k in h for h in headings for k in kws)
    ]
    if missing:
        return False, "Thiếu mục: " + ", ".join(missing) + "."
    return True, "Đủ 5 mục bắt buộc."


def check_steps_count(text: str) -> tuple[bool, str]:
    body = _section_body(text, REQUIRED_SECTIONS["Các bước"])
    if body is None:
        return False, "Không tìm thấy mục 'Các bước'."
    n = len(_STEP_RE.findall(body))
    if MIN_STEPS <= n <= MAX_STEPS:
        return True, f"Có {n} bước."
    return False, f"Có {n} bước đánh số; cần từ {MIN_STEPS} đến {MAX_STEPS} bước."


def check_length(text: str, max_words: int) -> tuple[bool, str]:
    n = count_words(text)
    if n <= max_words:
        return True, f"{n}/{max_words} từ."
    return False, f"{n} từ, vượt giới hạn {max_words} từ (cần rút gọn ít nhất {n - max_words} từ)."


# --- R5: title uses the topic's vocabulary -----------------------------------------

# Words a title may legitimately add without them being in the topic/body.
_TITLE_GENERIC = frozenset(
    "hướng dẫn cách bài cơ bản đơn giản nhanh chóng chi tiết từng bước đầu tiên và cho của với "
    "trên dưới trong bằng để từ đến về là có được khi như qua lên xuống ra vào các những một".split()
)


def check_title_matches_topic(text: str, topic: str | None = None) -> tuple[bool, str]:
    """
    Every word of the title must come from the topic or appear somewhere in the
    body. A title word found nowhere else (e.g. 'Ẩn' where the whole article says
    'ảo') is a hallucinated term and is reported with the word itself.
    """
    clean = strip_code_blocks(text)
    m = _H1_LINE_RE.search(clean)
    if not m:
        return True, "Không có tiêu đề để đối chiếu (đã báo ở R1)."
    title = m.group(1)
    body = text.replace(m.group(0), "", 1)
    known = set(_words(body)) | set(_words(topic or ""))
    unknown = [
        w for w in dict.fromkeys(_words(title))
        if len(w) >= 2 and not w.isdigit() and w not in known and w not in _TITLE_GENERIC
    ]
    if not unknown:
        return True, "Tiêu đề dùng đúng thuật ngữ của chủ đề."
    shown = ", ".join(f"'{w}'" for w in unknown)
    hint = f" Chủ đề là: \"{topic}\"." if topic else ""
    return False, (
        f"Tiêu đề có từ không xuất hiện trong chủ đề hay nội dung bài: {shown}. "
        f"Sửa tiêu đề dùng đúng thuật ngữ của chủ đề.{hint}"
    )


# --- R6: invisible characters --------------------------------------------------------


def check_invisible_chars(text: str) -> tuple[bool, str]:
    found = find_invisible_chars(text)
    if not found:
        return True, "Không có ký tự ẩn."
    shown = "; ".join(f"dòng {line}: {name}" for line, name in found[:3])
    more = f" (và {len(found) - 3} ký tự khác)" if len(found) > 3 else ""
    return False, f"Có {len(found)} ký tự ẩn/khoảng trắng đặc biệt — {shown}{more}. Xoá hoặc thay bằng khoảng trắng thường."


# --- R7: command order ---------------------------------------------------------------

# (trigger, prerequisite that must appear EARLIER, what is wrong, how to fix)
_PREREQUISITES: tuple[tuple[re.Pattern[str], re.Pattern[str], str, str], ...] = (
    (
        re.compile(r"\bgit\s+(?:add|commit|push|remote|status|log|diff|branch|checkout|pull|fetch)\b"),
        re.compile(r"\bgit\s+(?:init|clone)\b"),
        "cần một repository Git trên máy nhưng trước đó chưa có `git init` (hoặc `git clone`)",
        "thêm bước `git init` (trong thư mục dự án) trước bước này; nếu đây chỉ là bước kiểm tra "
        "cài đặt thì dùng lệnh không cần repository, ví dụ `git --version`",
    ),
    (
        re.compile(r"\bgit\s+commit\b"),
        re.compile(r"\bgit\s+add\b|\bgit\s+commit\s+[^&|;\n]*-\w*a"),
        "commit khi chưa có bước `git add` nào để đưa file vào vùng staging",
        "thêm bước `git add .` trước `git commit`",
    ),
    (
        re.compile(r"\bgit\s+push\b"),
        re.compile(r"\bgit\s+(?:commit|clone)\b"),
        "đẩy code khi chưa có commit nào",
        "thêm bước `git add .` rồi `git commit -m \"...\"` trước `git push`",
    ),
    (
        re.compile(r"(?:^|[\s/\\])activate\b"),
        re.compile(r"-m\s+venv\b|\bvirtualenv\b|\buv\s+venv\b|\bconda\s+create\b"),
        "kích hoạt môi trường ảo khi chưa có bước tạo môi trường ảo",
        "thêm bước tạo môi trường ảo (vd. `python -m venv venv`) trước bước kích hoạt",
    ),
)

_SNIPPET_RE = re.compile(r"```([^\n]*)\n(.*?)```|`([^`\n]+)`", re.DOTALL)
_SPLIT_CMD_RE = re.compile(r"\s*(?:&&|\|\||;|\n)\s*")
_PROMPT_RE = re.compile(r"^\s*(?:\$|>|PS\s[^>\n]*>|[A-Za-z]:\\[^>\n]*>)\s*")
_INSTALL_TARGET_RE = re.compile(r"(?:cài đặt|cài|install|setup)\s+([a-z0-9][\w.+-]*)", re.IGNORECASE)
_VERSION_CMD_RE = re.compile(r"^\s*([\w.+-]+?)(?:\.exe)?\s+(?:--version|-v|-V|version)\b")
_INSTALL_WORDS_RE = re.compile(r"tải|cài đặt|download|install", re.IGNORECASE)


@dataclass
class _Command:
    pos: int  # offset in the combined text (preparation + steps + verification)
    text: str  # a single shell command (already split on && ; newline)
    earlier_in_snippet: str  # commands that came before it inside the same snippet


def _iter_commands(combined: str) -> list[_Command]:
    commands: list[_Command] = []
    for m in _SNIPPET_RE.finditer(combined):
        raw = m.group(2) if m.group(2) is not None else m.group(3)
        earlier: list[str] = []
        for part in _SPLIT_CMD_RE.split(raw):
            part = _PROMPT_RE.sub("", part).strip()
            if not part or part.startswith("#"):
                continue
            commands.append(_Command(m.start(), part, " ".join(earlier)))
            earlier.append(part)
    return commands


def check_command_order(text: str, topic: str | None = None) -> tuple[bool, str]:
    """
    Walk through the commands in the order a reader would run them (Chuẩn bị ->
    Các bước -> Kiểm tra kết quả) and report any command that depends on a
    command that has not appeared yet.
    """
    prep = _raw_section(text, REQUIRED_SECTIONS["Chuẩn bị"])
    steps = _raw_section(text, REQUIRED_SECTIONS["Các bước"])
    verify = _raw_section(text, REQUIRED_SECTIONS["Kiểm tra kết quả"])
    combined = prep + "\n" + steps + "\n" + verify
    steps_start, steps_end = len(prep) + 1, len(prep) + 1 + len(steps)

    masked_steps = _mask_code_blocks(steps)
    step_starts = [steps_start + m.start() for m in _STEP_RE.finditer(masked_steps)]
    step_slices = list(zip(step_starts, step_starts[1:] + [steps_end]))

    def where(pos: int) -> str:
        if pos < steps_start:
            return "mục Chuẩn bị"
        if pos >= steps_end:
            return "mục Kiểm tra kết quả"
        return f"bước {max(bisect_right(step_starts, pos), 1)}"

    def step_index(pos: int) -> int | None:
        if steps_start <= pos < steps_end:
            return max(bisect_right(step_starts, pos), 1)
        return None

    title_m = _H1_LINE_RE.search(strip_code_blocks(text))
    targets = {
        t.lower()
        for t in _INSTALL_TARGET_RE.findall(f"{topic or ''} {title_m.group(1) if title_m else ''}")
    }

    problems: list[str] = []
    reported_rules: set[int] = set()
    reported_version = False

    for cmd in _iter_commands(combined):
        before = combined[: cmd.pos] + " " + cmd.earlier_in_snippet

        for i, (trigger, prereq, wrong, fix) in enumerate(_PREREQUISITES):
            if i in reported_rules or not trigger.search(cmd.text) or prereq.search(before):
                continue
            reported_rules.add(i)
            problems.append(f"{where(cmd.pos).capitalize()}: `{cmd.text}` {wrong}; {fix}.")

        vm = _VERSION_CMD_RE.match(cmd.text)
        idx = step_index(cmd.pos)
        if vm and idx is not None and not reported_version and vm.group(1).lower() in targets:
            earlier_prose = [
                re.sub(r"`[^`]*`", " ", combined[a:b]) for a, b in step_slices[: idx - 1]
            ]
            if not any(_INSTALL_WORDS_RE.search(prose) for prose in earlier_prose):
                reported_version = True
                tool = vm.group(1)
                problems.append(
                    f"Bước {idx}: `{cmd.text}` kiểm tra phiên bản {tool} trước khi có bước tải/cài đặt "
                    f"{tool}; chuyển lệnh kiểm tra xuống sau bước cài đặt (hoặc sang mục Kiểm tra kết quả)."
                )

    if problems:
        return False, " ".join(problems)
    return True, "Trình tự lệnh hợp lý."


# --- R8: hard-coded secrets ------------------------------------------------------------

_SECRET_ASSIGN_RE = re.compile(
    r"""(?P<name>[A-Za-z_][\w.]*)\s*[=:]\s*(?P<q>["'])(?P<val>[^"'\n]+)(?P=q)"""
)
_SECRET_NAME_RE = re.compile(r"api[_-]?key|access[_-]?key|secret|token|passw(?:or)?d", re.IGNORECASE)
_SHELL_ENV_LINE_RE = re.compile(r"^\s*(?:export\s|set\s|setx\s|\$env:|\[environment\])", re.IGNORECASE)
_PROGRAMMING_LANGS = frozenset(
    "python py javascript js typescript ts java go ruby rb php csharp cs rust kotlin swift".split()
)
_ENV_NAME_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*_(?:API_KEY|KEY|TOKEN|SECRET)\b")


def check_hardcoded_secrets(text: str) -> tuple[bool, str]:
    """
    Flag `api_key="..."`-style assignments in code. Lines that SET an environment
    variable in a shell (`export X=...`, `setx X ...`, `$env:X=...`) are allowed:
    that is exactly what a tutorial should tell the reader to do.
    """
    env_names = _ENV_NAME_RE.findall(text)
    suggestion = env_names[0] if env_names else "TÊN_BIẾN_MÔI_TRƯỜNG"
    offenders: list[str] = []
    for m in _SNIPPET_RE.finditer(text):
        lang = (m.group(1) or "").strip().lower() if m.group(2) is not None else ""
        raw = m.group(2) if m.group(2) is not None else m.group(3)
        for line in raw.splitlines():
            if _SHELL_ENV_LINE_RE.match(line):
                continue
            for a in _SECRET_ASSIGN_RE.finditer(line):
                name = a.group("name")
                if not _SECRET_NAME_RE.search(name):
                    continue
                # In a code block of a programming language any literal is a problem; elsewhere
                # (.env / shell snippets) ALL_CAPS names are configuration, not code.
                if lang in _PROGRAMMING_LANGS or name != name.upper():
                    offenders.append(a.group(0))
    if not offenders:
        return True, "Không có khóa/token gán cứng trong mã."
    shown = ", ".join(f"`{o}`" for o in dict.fromkeys(offenders))
    return False, (
        f"Mã gán cứng khóa/bí mật: {shown}. Đọc khóa từ biến môi trường, ví dụ "
        f"`os.environ[\"{suggestion}\"]` (hoặc bỏ tham số để thư viện tự đọc biến môi trường), "
        "và không viết giá trị khóa trong mã."
    )


# --- Public API ------------------------------------------------------------------


def run_rule_checks(text: str, max_words: int, topic: str | None = None) -> list[ItemResult]:
    """Run R1-R8 on `text`. Pure function: no LLM, no side effects."""
    outcomes = {
        "R1": check_title(text),
        "R2": check_sections(text),
        "R3": check_steps_count(text),
        "R4": check_length(text, max_words),
        "R5": check_title_matches_topic(text, topic),
        "R6": check_invisible_chars(text),
        "R7": check_command_order(text, topic),
        "R8": check_hardcoded_secrets(text),
    }
    results = []
    for item in RULE_ITEMS:
        passed, comment = outcomes[item.id]
        results.append(
            ItemResult(
                id=item.id,
                description=item.description,
                kind="rule",
                passed=passed,
                comment=comment,
            )
        )
    return results
