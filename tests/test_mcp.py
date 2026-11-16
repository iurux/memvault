import asyncio
import json

import pytest

from memvault import mcp_server
from memvault.vault import Vault


@pytest.fixture(autouse=True)
def fresh_vault(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "_vault", Vault(tmp_path / "mcp.db"))


def call(name, **args):
    r = asyncio.run(mcp_server.server.call_tool(name, args))
    sc = r.structured_content
    if sc is None:  # tools returning a plain dict come back as JSON text
        return json.loads(r.content[0].text)
    return sc["result"] if set(sc) == {"result"} else sc


def test_note_edit_append_and_metadata():
    cid = call("save_note", title="Groceries", content="eggs", tags=["home"]).split()[-1]
    call("edit_note", conversation_id=cid, content="eggs, milk")
    call("edit_note", conversation_id=cid, content="also bread", mode="append")
    call("update_conversation", conversation_id=cid, title="Shopping", starred=True)
    c = call("get_conversation", conversation_id=cid)
    assert [m["content"] for m in c["messages"]] == ["eggs, milk", "also bread"]
    assert c["title"] == "Shopping" and c["tags"] == ["home"] and c["starred"] is True
    assert call("search_memory", query="bread")[0]["id"] == cid
    assert call("edit_note", conversation_id="nope", content="x") == "not found"
    assert call("delete_conversation", conversation_id=cid) == "deleted"
