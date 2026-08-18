import os
import unittest
from unittest.mock import patch

os.environ.setdefault("MCP_AUTH_MODE", "static")
os.environ.setdefault("MCP_STATIC_TOKEN", "local-test-token-at-least-24-characters")
os.environ.setdefault("MCP_ALLOWED_GITHUB_LOGIN", "swsecret12-ux")

import mcp_server


class AuthTest(unittest.TestCase):
    def test_allowed_login(self):
        self.assertEqual(
            mcp_server.authorize_claims({"login": "swsecret12-ux"}, "swsecret12-ux"),
            "swsecret12-ux",
        )

    def test_other_login_is_denied(self):
        with self.assertRaises(PermissionError):
            mcp_server.authorize_claims({"login": "someone-else"}, "swsecret12-ux")

    def test_missing_production_secret_fails_closed(self):
        with patch.dict(os.environ, {"MCP_AUTH_MODE": "github"}, clear=True):
            with self.assertRaises(RuntimeError):
                mcp_server.build_auth()


class ToolContractTest(unittest.IsolatedAsyncioTestCase):
    async def test_all_tools_are_read_only(self):
        tools = await mcp_server.mcp.list_tools()
        self.assertEqual(len(tools), 9)
        self.assertTrue(all(tool.annotations.readOnlyHint for tool in tools))
        self.assertTrue(all(not tool.annotations.destructiveHint for tool in tools))
        open_world = {tool.name for tool in tools if tool.annotations.openWorldHint}
        self.assertEqual(open_world, {"get_market_snapshot"})


if __name__ == "__main__":
    unittest.main()
