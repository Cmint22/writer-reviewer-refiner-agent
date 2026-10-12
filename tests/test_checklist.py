from app.checklist import (
    CHECKLIST,
    check_length,
    check_sections,
    check_steps_count,
    check_title,
    count_words,
    run_rule_checks,
)
from tests.conftest import GOOD_TUTORIAL


def test_checklist_has_eight_rule_and_four_llm_items_with_unique_ids():
    ids = [c.id for c in CHECKLIST]
    assert len(ids) == len(set(ids)) == 12
    assert [c.id for c in CHECKLIST if c.kind == "rule"] == [f"R{i}" for i in range(1, 9)]
    assert [c.id for c in CHECKLIST if c.kind == "llm"] == ["L1", "L2", "L3", "L4"]


def test_good_tutorial_passes_all_rules():
    results = run_rule_checks(GOOD_TUTORIAL, max_words=350)
    assert [r.id for r in results] == [f"R{i}" for i in range(1, 9)]
    assert all(r.passed for r in results), [r.comment for r in results if not r.passed]


def test_title_rule():
    assert check_title("# Tiêu đề\nnội dung")[0]
    assert not check_title("## Chỉ có mục cấp 2")[0]
    # A '# comment' inside a code block is not a title.
    assert not check_title("```bash\n# comment\n```")[0]


def test_sections_rule_reports_missing_sections():
    text = GOOD_TUTORIAL.replace("## Lỗi thường gặp", "## Ghi chú")
    ok, comment = check_sections(text)
    assert not ok and "Lỗi thường gặp" in comment


def test_steps_count_bounds():
    def tutorial(n):
        steps = "\n".join(f"{i}. Làm việc {i}." for i in range(1, n + 1))
        return f"# T\n\n## Các bước\n{steps}\n\n## Kiểm tra kết quả\nok\n"

    assert not check_steps_count(tutorial(2))[0]
    assert check_steps_count(tutorial(3))[0]
    assert check_steps_count(tutorial(8))[0]
    assert not check_steps_count(tutorial(9))[0]
    assert not check_steps_count("# T\n\n## Mục tiêu\nx")[0]  # no steps section


def test_length_ignores_code_blocks():
    prose = "từ " * 10
    code = "```\n" + "x " * 500 + "\n```"
    assert count_words(prose + code) == 10
    assert check_length(prose + code, max_words=10)[0]
    ok, comment = check_length("từ " * 30, max_words=10)
    assert not ok and "20" in comment  # needs to cut at least 20 words
