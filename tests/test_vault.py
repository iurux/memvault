import json

import numpy as np
import pytest

from memvault import Conversation, Message, Vault, importers
from memvault.cli import main
from memvault.vault import chunk_messages


class FakeEmbedder:
    """Deterministic bag-of-characters embedding so tests run without Ollama."""

    model = "fake"

    def embed(self, texts):
        out = np.zeros((len(texts), 64), dtype=np.float32)
        for i, t in enumerate(texts):
            for ch in t.lower():
                out[i, ord(ch) % 64] += 1
        return out


@pytest.fixture
def vault(tmp_path):
    v = Vault(tmp_path / "v.db", embedder=FakeEmbedder())
    yield v
    v.close()


def conv(title, *pairs, **kw):
    msgs = []
    for u, a in pairs:
        msgs += [Message("user", u), Message("assistant", a)]
    return Conversation(messages=msgs, title=title, **kw)


def test_save_get_roundtrip(vault):
    c = conv("Bread", ("how long to proof sourdough", "usually 4-12 hours"), tags=["baking"])
    vault.save(c)
    got = vault.get(c.id)
    assert got.title == "Bread"
    assert got.tags == ["baking"]
    assert [m.role for m in got.messages] == ["user", "assistant"]


def test_keyword_search(vault):
    vault.save(conv("Hiking", ("plan a mountain hike", "Rainier and Olympic trails")))
    vault.save(conv("Cooking", ("how to make ramen broth", "simmer pork bones")))
    hits = vault.search("Olympic")
    assert hits and hits[0].title == "Hiking"


def test_short_cjk_terms(vault):
    vault.save(conv("饺子", ("饺子馅怎么调", "白菜猪肉")))
    vault.save(conv("other", ("hello", "world")))
    assert vault.search("饺子")[0].title == "饺子"


def test_search_without_embedder(tmp_path):
    v = Vault(tmp_path / "k.db")
    v.save(conv("Networking", ("explain TCP congestion control", "AIMD, slow start")))
    assert v.search("congestion")[0].title == "Networking"


def test_replace_and_delete(vault):
    c = conv("v1", ("a question here", "an answer here"))
    vault.save(c)
    c.title = "v2"
    vault.save(c)
    assert len(vault.list()) == 1 and vault.get(c.id).title == "v2"
    assert vault.delete(c.id)
    assert vault.search("question") == []


def test_list_filter_by_tag(vault):
    vault.save(conv("a", ("x" * 5, "y" * 5), tags=["work"]))
    vault.save(conv("b", ("x" * 5, "y" * 5), tags=["life"]))
    assert [r["title"] for r in vault.list(tag="work")] == ["a"]


def test_chunking_splits_long_text():
    chunks = chunk_messages([Message("user", "z" * 3000)], limit=1000)
    assert len(chunks) >= 3 and all(len(c) <= 1000 for c in chunks)


def test_claude_import(tmp_path):
    data = [
        {
            "uuid": "abc",
            "name": "Test chat",
            "created_at": "2026-01-01T00:00:00Z",
            "chat_messages": [
                {"sender": "human", "text": "hi there", "created_at": "2026-01-01T00:00:00Z"},
                {"sender": "assistant", "text": "hello!", "created_at": "2026-01-01T00:00:01Z"},
            ],
        }
    ]
    convs = list(importers.claude_export(data))
    assert convs[0].id == "claude-abc"
    assert [m.role for m in convs[0].messages] == ["user", "assistant"]


def test_chatgpt_import_follows_current_branch():
    data = [
        {
            "title": "GPT chat",
            "conversation_id": "c1",
            "create_time": 1700000000,
            "current_node": "n3",
            "mapping": {
                "root": {"message": None, "parent": None},
                "n1": {"parent": "root", "message": {"author": {"role": "user"}, "content": {"parts": ["question"]}}},
                "n2": {"parent": "n1", "message": {"author": {"role": "assistant"}, "content": {"parts": ["old answer"]}}},
                "n3": {"parent": "n1", "message": {"author": {"role": "assistant"}, "content": {"parts": ["new answer"]}}},
            },
        }
    ]
    (c,) = importers.chatgpt_export(data)
    assert [m.content for m in c.messages] == ["question", "new answer"]


def test_cli_import_and_search(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("MEMVAULT_EMBEDDER", "none")
    export = tmp_path / "conversations.json"
    export.write_text(
        json.dumps(
            [{"uuid": "u1", "name": "Garden notes", "chat_messages": [
                {"sender": "human", "text": "planting tomatoes in spring"},
                {"sender": "assistant", "text": "full sun, water daily"},
            ]}]
        )
    )
    db = str(tmp_path / "cli.db")
    main(["--db", db, "import", str(export)])
    main(["--db", db, "search", "tomatoes"])
    out = capsys.readouterr().out
    assert "imported 1" in out and "Garden notes" in out
