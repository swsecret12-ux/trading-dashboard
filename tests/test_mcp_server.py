import os
import unittest
from unittest.mock import patch

os.environ.setdefault("MCP_AUTH_MODE", "static")
os.environ.setdefault("MCP_STATIC_TOKEN", "local-test-token-at-least-24-characters")
os.environ.setdefault("MCP_ALLOWED_GITHUB_LOGIN", "test-owner")

import mcp_server


class AuthTest(unittest.TestCase):
    def test_allowed_login(self):
        self.assertEqual(
            mcp_server.authorize_claims({"login": "test-owner"}, "test-owner"),
            "test-owner",
        )

    def test_other_login_is_denied(self):
        with self.assertRaises(PermissionError):
            mcp_server.authorize_claims({"login": "someone-else"}, "test-owner")

    def test_missing_production_secret_fails_closed(self):
        with patch.dict(os.environ, {"MCP_AUTH_MODE": "github"}, clear=True):
            with self.assertRaises(RuntimeError):
                mcp_server.build_auth()

    def test_github_oauth_uses_prefixed_operational_routes(self):
        env = {
            "MCP_AUTH_MODE": "github",
            "MCP_BASE_URL": "https://example.test",
            "MCP_ALLOWED_GITHUB_LOGIN": "test-owner",
            "MCP_JWT_SIGNING_KEY": "test-signing-key-at-least-24-characters",
            "GITHUB_CLIENT_ID": "test-client-id",
            "GITHUB_CLIENT_SECRET": "test-client-secret",
        }
        with patch.dict(os.environ, env, clear=True):
            auth = mcp_server.build_auth()

        self.assertEqual(str(auth.base_url).rstrip("/"), "https://example.test/oauth")
        self.assertEqual(
            str(auth.resource_base_url).rstrip("/"), "https://example.test"
        )
        self.assertEqual(str(auth.issuer_url).rstrip("/"), "https://example.test")

    def test_oauth_prefix_is_rewritten_for_the_inner_app(self):
        captured = {}

        async def inner(scope, receive, send):
            captured.update(scope)

        middleware = mcp_server.OAuthPrefixMiddleware(inner)

        async def exercise():
            await middleware(
                {
                    "type": "http",
                    "path": "/oauth/register",
                    "raw_path": b"/oauth/register",
                },
                None,
                None,
            )

        import asyncio

        asyncio.run(exercise())
        self.assertEqual(captured["path"], "/register")
        self.assertEqual(captured["raw_path"], b"/register")


class ToolContractTest(unittest.IsolatedAsyncioTestCase):
    async def test_all_tools_are_read_only(self):
        tools = await mcp_server.mcp.list_tools()
        self.assertEqual(len(tools), 10)
        self.assertTrue(all(tool.annotations.readOnlyHint for tool in tools))
        self.assertTrue(all(not tool.annotations.destructiveHint for tool in tools))
        open_world = {tool.name for tool in tools if tool.annotations.openWorldHint}
        self.assertEqual(
            open_world,
            {"get_market_snapshot", "get_chart_analysis_context"},
        )


if __name__ == "__main__":
    unittest.main()
