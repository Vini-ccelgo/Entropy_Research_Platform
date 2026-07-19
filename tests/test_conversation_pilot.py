import json
from pathlib import Path
from uuid import uuid4

import pytest

from core.mvp import build_and_register
from core.types import ChatMessage, ChatRole, ModelRequest, RenderedPrompt, TrialStatus
from database.sqlite_repository import SqliteRepository
from models.lmstudio import LmStudioProvider


def test_chat_message_hash_includes_role_and_content():
    user = ChatMessage(role=ChatRole.USER, content="same")
    assistant = ChatMessage(role=ChatRole.ASSISTANT, content="same")
    assert user.content_hash != assistant.content_hash
    assert ChatMessage(role=ChatRole.USER, content="same").content_hash == user.content_hash


def test_pilot_allocations_and_max_tokens(tmp_path: Path):
    for filename, expected, max_tokens, trajectories_expected in (("broad-prompt-pilot.json", 32, 256, None), ("self-directed-conversation-pilot.json", 24, 256, 4), ("mixed-question-pretest.json", 56, 512, None), ("self-directed-conversation-expanded.json", 48, 512, 8)):
        repo = SqliteRepository(tmp_path / f"{filename}.db")
        _, experiment = build_and_register(Path("config/experiments") / filename, repo)
        assert len(experiment.plan.trials) == expected
        assert {trial.max_tokens for trial in experiment.plan.trials} == {max_tokens}
        assert {trial.condition_id for trial in experiment.plan.trials} == {"control", "os-entropy"}
        if trajectories_expected:
            trajectories = {}
            for trial in experiment.plan.trials:
                trajectories.setdefault(trial.conversation.trajectory_id, []).append(trial)
            assert len(trajectories) == trajectories_expected
            assert all([turn.conversation.turn_index for turn in sorted(turns, key=lambda item: item.conversation.turn_index)] == list(range(1, 7)) for turns in trajectories.values())


def test_lmstudio_payload_uses_ordered_messages_and_max_tokens(monkeypatch):
    sent = {}
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}], "usage": {}}
    def post(url, json, timeout):
        sent.update(json); return Response()
    monkeypatch.setattr("models.lmstudio.httpx.post", post)
    request = ModelRequest(provider="lmstudio", model_identifier="model", prompt=RenderedPrompt(template_id="p", template_version="1", text="ignored"),
        messages=(ChatMessage(role=ChatRole.USER, content="first"), ChatMessage(role=ChatRole.ASSISTANT, content="reply"), ChatMessage(role=ChatRole.USER, content="continue")), temperature=.9, top_p=.95, max_tokens=256, seed=1)
    LmStudioProvider(model_artifact_hashes={}).generate(request)
    assert sent["max_tokens"] == 256
    assert sent["messages"] == [{"role": "user", "content": "first"}, {"role": "assistant", "content": "reply"}, {"role": "user", "content": "continue"}]


def test_lmstudio_payload_supports_pretest_max_tokens_512(monkeypatch):
    sent = {}
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}], "usage": {}}
    monkeypatch.setattr("models.lmstudio.httpx.post", lambda url, json, timeout: (sent.update(json) or Response()))
    request = ModelRequest(provider="lmstudio", model_identifier="model", prompt=RenderedPrompt(template_id="p", template_version="1", text="question"), temperature=.9, top_p=.95, max_tokens=512)
    LmStudioProvider().generate(request)
    assert sent["max_tokens"] == 512


def test_chat_request_rejects_malformed_role_ordering():
    with pytest.raises(ValueError, match="cannot begin with an assistant"):
        ModelRequest(provider="x", model_identifier="m", prompt=RenderedPrompt(template_id="p", template_version="1", text="x"),
            messages=(ChatMessage(role=ChatRole.ASSISTANT, content="not allowed"),), temperature=.9, top_p=.95)
