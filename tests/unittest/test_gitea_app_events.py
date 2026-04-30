import pytest

from pr_agent.servers import gitea_app


class DummyAgent:
    pass


class FakeSettings:
    def get(self, key, default=None):
        values = {
            "gitea.push_commands": ["/review -i"],
            "gitea.handle_push_trigger": True,
        }
        return values.get(key, default)


@pytest.mark.asyncio
async def test_pull_request_sync_event_runs_push_commands(monkeypatch):
    calls = []

    async def perform_commands(commands_conf, agent, body, api_url):
        calls.append((commands_conf, api_url))

    monkeypatch.setattr(gitea_app, "PRAgent", DummyAgent)
    monkeypatch.setattr(gitea_app, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(gitea_app, "should_process_pr_logic", lambda body: True)
    monkeypatch.setattr(gitea_app, "_perform_commands_gitea", perform_commands)

    await gitea_app.handle_request(
        {"action": "synchronized", "pull_request": {"url": "http://devstar.local/api/v1/repos/o/r/pulls/1"}},
        event="pull_request_sync",
    )

    assert calls == [("push_commands", "http://devstar.local/api/v1/repos/o/r/pulls/1")]


@pytest.mark.asyncio
async def test_pull_request_comment_event_runs_slash_command(monkeypatch):
    calls = []

    class CommentAgent:
        async def handle_request(self, pr_url, command):
            calls.append((pr_url, command))

    monkeypatch.setattr(gitea_app, "PRAgent", CommentAgent)

    await gitea_app.handle_request(
        {
            "action": "created",
            "pull_request": {"url": "http://devstar.local/api/v1/repos/o/r/pulls/1"},
            "comment": {"body": "/review"},
        },
        event="pull_request_comment",
    )

    assert calls == [("http://devstar.local/api/v1/repos/o/r/pulls/1", "/review")]
