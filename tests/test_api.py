import pytest
from starlette.testclient import TestClient

from memvault import Conversation, Message, Vault
from memvault.api import create_app


@pytest.fixture
def client(tmp_path):
    v = Vault(tmp_path / "api.db")
    v.save(Conversation(
        messages=[Message("user", "番茄炒蛋 recipe sourdough"), Message("assistant", "先炒蛋再炒番茄")],
        title="Cooking", tags=["food", "recipes"], id="c1",
    ))
    v.save(Conversation(messages=[Message("user", "TCP congestion control")], title="Networking", tags=["cs"], id="c2"))
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "index.html").write_text("<html>ui</html>")
    return TestClient(create_app(v, static_dir=tmp_path / "dist"))


def test_list_and_filter(client):
    r = client.get("/api/conversations")
    assert r.status_code == 200 and {c["id"] for c in r.json()} == {"c1", "c2"}
    assert r.json()[0]["snippet"]
    assert [c["id"] for c in client.get("/api/conversations?tag=cs").json()] == ["c2"]


def test_get_and_404(client):
    r = client.get("/api/conversations/c1").json()
    assert r["tags"] == ["food", "recipes"] and r["messages"][1]["role"] == "assistant"
    assert client.get("/api/conversations/nope").status_code == 404


def test_patch(client):
    r = client.patch("/api/conversations/c1", json={"title": "Cooking 2", "tags": ["food"]})
    assert r.status_code == 200 and r.json()["title"] == "Cooking 2" and r.json()["tags"] == ["food"]
    assert client.patch("/api/conversations/c1", json={"tags": "bad"}).status_code == 400
    assert client.patch("/api/conversations/x", json={"title": "y"}).status_code == 404


def test_delete(client):
    assert client.delete("/api/conversations/c2").status_code == 204
    assert client.get("/api/conversations/c2").status_code == 404


def test_search_and_tags(client):
    assert client.get("/api/search", params={"q": "sourdough"}).json()[0]["conversation_id"] == "c1"
    assert client.get("/api/search", params={"q": "番茄"}).json()[0]["conversation_id"] == "c1"
    assert client.get("/api/search?q=").json() == []
    assert {"tag": "food", "count": 1} in client.get("/api/tags").json()


def test_create_note(client):
    r = client.post("/api/notes", json={"title": "n", "content": "remember this", "tags": ["x"]})
    assert r.status_code == 201
    assert client.get(f"/api/conversations/{r.json()['id']}").json()["messages"][0]["role"] == "note"
    assert client.post("/api/notes", json={"content": ""}).status_code == 400


def test_cors_lovable_and_localhost(client):
    for origin in ["https://abc-123.lovable.app", "http://localhost:5173"]:
        r = client.options("/api/tags", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
        assert r.headers.get("access-control-allow-origin") == origin
    r = client.options("/api/tags", headers={"Origin": "https://evil.com", "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") is None


def test_static_spa_fallback(client):
    assert client.get("/").text == "<html>ui</html>"
    assert client.get("/c/c1").text == "<html>ui</html>"


def test_archive_flow(client):
    r = client.patch("/api/conversations/c2", json={"archived": True})
    assert r.status_code == 200 and r.json()["archived"] is True
    assert [c["id"] for c in client.get("/api/conversations").json()] == ["c1"]
    assert [c["id"] for c in client.get("/api/conversations?archived=true").json()] == ["c2"]
    assert len(client.get("/api/conversations?archived=all").json()) == 2
    assert client.get("/api/search", params={"q": "congestion"}).json() == []
    assert client.get("/api/search", params={"q": "congestion", "include_archived": "true"}).json()
    assert client.patch("/api/conversations/c2", json={"archived": "yes"}).status_code == 400
    assert client.patch("/api/conversations/c2", json={"archived": False}).json()["archived"] is False
