import inspect

import pytest

from app.agents.writer import WriterAgent, strip_outer_code_fence
from app.schemas import Draft
from tests.fakes import BAD_DRAFT, FakeLLMClient


def test_writer_signature_takes_only_the_request():
    assert list(inspect.signature(WriterAgent.run).parameters) == ["self", "request"]


def test_writer_returns_draft_carrying_the_brief(request_obj):
    draft = WriterAgent(FakeLLMClient()).run(request_obj)
    assert isinstance(draft, Draft)
    assert draft.content == BAD_DRAFT.strip()
    assert (draft.topic, draft.audience, draft.max_words) == (
        request_obj.topic, request_obj.audience, request_obj.max_words,
    )


def test_writer_prompt_contains_topic_audience_and_limit(request_obj):
    seen = {}

    class Spy:
        def chat(self, system_prompt, user_prompt):
            seen["user"] = user_prompt
            return "# T"

    WriterAgent(Spy()).run(request_obj)
    assert request_obj.topic in seen["user"]
    assert request_obj.audience in seen["user"]
    assert "350" in seen["user"]


def test_writer_does_not_see_the_checklist(request_obj):
    seen = {}

    class Spy:
        def chat(self, system_prompt, user_prompt):
            seen["all"] = system_prompt + user_prompt
            return "# T"

    WriterAgent(Spy()).run(request_obj)
    assert "CHECKLIST" not in seen["all"]


def test_writer_rejects_empty_output(request_obj):
    class Empty:
        def chat(self, s, u):
            return "   "

    with pytest.raises(RuntimeError):
        WriterAgent(Empty()).run(request_obj)


def test_strip_outer_code_fence_only_removes_a_wrapping_fence():
    assert strip_outer_code_fence("```markdown\n# T\n\ntext\n```") == "# T\n\ntext"
    inner = "# T\n\n```bash\nls\n```"
    assert strip_outer_code_fence(inner) == inner
