from datetime import datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pr_agent.git_providers.git_provider import IncrementalPR
from pr_agent.git_providers.gitea_provider import GiteaProvider


class TestGiteaProvider:
    @patch('pr_agent.git_providers.gitea_provider.get_settings')
    @patch('pr_agent.git_providers.gitea_provider.giteapy.ApiClient')
    def test_gitea_provider_auth_header(self, mock_api_client_cls, mock_get_settings):
        # Setup settings
        settings = MagicMock()
        settings.get.side_effect = lambda k, d=None: {
            'GITEA.URL': 'https://gitea.example.com',
            'GITEA.PERSONAL_ACCESS_TOKEN': 'test-token',
            'GITEA.REPO_SETTING': None,
            'GITEA.SKIP_SSL_VERIFICATION': False,
            'GITEA.SSL_CA_CERT': None
        }.get(k, d)
        mock_get_settings.return_value = settings

        # Setup ApiClient mock
        mock_api_client = mock_api_client_cls.return_value
        # Mock configuration object on client
        mock_api_client.configuration.api_key = {'Authorization': 'token test-token'}

        # Mock responses for calls made during initialization
        def call_api_side_effect(path, method, **kwargs):
            mock_resp = MagicMock()
            if 'files' in path: # get_change_file_pull_request
                mock_resp.data = BytesIO(b'[]')
                return mock_resp
            if 'commits' in path:
                mock_resp.data = BytesIO(b'[]')
                return mock_resp

            # Default fallback
            mock_resp.data = BytesIO(b'{}')
            return mock_resp

        mock_api_client.call_api.side_effect = call_api_side_effect

        from pr_agent.git_providers.gitea_provider import RepoApi

        client = mock_api_client
        repo_api = RepoApi(client)

        # Now test methods independently

        # 1. get_change_file_pull_request
        mock_api_client.reset_mock()
        mock_resp = MagicMock()
        mock_resp.data = BytesIO(b'[]')
        mock_api_client.call_api.return_value = mock_resp

        repo_api.get_change_file_pull_request('owner', 'repo', 123)

        args, kwargs = mock_api_client.call_api.call_args
        assert '/repos/owner/repo/pulls/123/files' in args[0]
        assert kwargs.get('auth_settings') == ['AuthorizationHeaderToken']
        assert 'token=' not in args[0]

        # 2. get_pull_request_diff
        mock_api_client.reset_mock()
        mock_resp = MagicMock()
        mock_resp.data = BytesIO(b'diff content')
        mock_api_client.call_api.return_value = mock_resp

        repo_api.get_pull_request_diff('owner', 'repo', 123)

        args, kwargs = mock_api_client.call_api.call_args
        assert args[0] == '/repos/owner/repo/pulls/123.diff'
        assert kwargs.get('auth_settings') == ['AuthorizationHeaderToken']

        # 3. get_languages
        mock_api_client.reset_mock()
        mock_resp.data = BytesIO(b'{"Python": 100}')
        mock_api_client.call_api.return_value = mock_resp

        repo_api.get_languages('owner', 'repo')

        args, kwargs = mock_api_client.call_api.call_args
        assert args[0] == '/repos/owner/repo/languages'
        assert kwargs.get('auth_settings') == ['AuthorizationHeaderToken']

        # 4. get_file_content
        mock_api_client.reset_mock()
        mock_resp.data = BytesIO(b'content')
        mock_api_client.call_api.return_value = mock_resp

        repo_api.get_file_content('owner', 'repo', 'sha1', 'file.txt')

        args, kwargs = mock_api_client.call_api.call_args
        assert args[0] == '/repos/owner/repo/raw/file.txt'
        assert kwargs.get('query_params') == [('ref', 'sha1')]
        assert kwargs.get('auth_settings') == ['AuthorizationHeaderToken']

        # 5. get_pr_commits
        mock_api_client.reset_mock()
        mock_resp.data = BytesIO(b'[]')
        mock_api_client.call_api.return_value = mock_resp

        repo_api.get_pr_commits('owner', 'repo', 123)

        args, kwargs = mock_api_client.call_api.call_args
        assert args[0] == '/repos/owner/repo/pulls/123/commits'
        assert kwargs.get('auth_settings') == ['AuthorizationHeaderToken']

    def test_gitea_incremental_commits_uses_previous_review(self):
        provider = object.__new__(GiteaProvider)
        provider.logger = MagicMock()
        provider.owner = "owner"
        provider.repo = "repo"
        provider.pr_number = 1
        provider.base_ref = "main"
        provider.unreviewed_files_set = {}
        provider.pr_commits = GiteaProvider._normalize_commits([
            {
                "sha": "new",
                "html_url": "https://gitea.local/owner/repo/commit/new",
                "created": "2026-04-30T19:02:02Z",
                "commit": {
                    "message": "add average helper\n",
                    "author": {"date": "2026-04-30T19:02:02Z"},
                },
                "files": [{"filename": "src/calculator.py", "status": "modified"}],
            },
            {
                "sha": "old",
                "html_url": "https://gitea.local/owner/repo/commit/old",
                "created": "2026-04-30T18:59:59Z",
                "commit": {
                    "message": "add calculator helpers\n",
                    "author": {"date": "2026-04-30T18:59:59Z"},
                },
                "files": [{"filename": "src/calculator.py", "status": "added"}],
            },
        ])
        provider.get_previous_review = MagicMock(
            return_value=SimpleNamespace(
                created_at=datetime(2026, 4, 30, 19, 0, 40),
                html_url="https://gitea.local/owner/repo/pulls/1#issuecomment-117",
            )
        )

        incremental = IncrementalPR(True)

        provider.get_incremental_commits(incremental)

        assert incremental.is_incremental
        assert incremental.first_new_commit_sha == "new"
        assert incremental.last_seen_commit_sha == "old"
        assert [commit.sha for commit in incremental.commits_range] == ["new"]
        assert list(provider.unreviewed_files_set) == ["src/calculator.py"]

    def test_gitea_incremental_commits_falls_back_without_previous_review(self):
        provider = object.__new__(GiteaProvider)
        provider.logger = MagicMock()
        provider.owner = "owner"
        provider.repo = "repo"
        provider.pr_number = 1
        provider.unreviewed_files_set = {}
        provider.pr_commits = []
        provider.get_previous_review = MagicMock(return_value=None)

        incremental = IncrementalPR(True)

        provider.get_incremental_commits(incremental)

        assert not incremental.is_incremental
        assert incremental.commits_range == []
