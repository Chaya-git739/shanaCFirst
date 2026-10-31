"""Offline SDK option checks; no SDK import or model call is required."""

import unittest

from SDK.agent import EFFORT, MODEL, SYSTEM_PROMPT, TOOL_NAMES, sdk_config


class SdkConfigTests(unittest.TestCase):
    def test_sdk_uses_custom_prompt_small_allowlist_and_strict_mcp(self) -> None:
        config = sdk_config()
        self.assertEqual(config["model"], MODEL)
        self.assertEqual(config["effort"], EFFORT)
        self.assertEqual(config["system_prompt"]["type"], "custom")
        self.assertEqual(config["system_prompt"]["prompt"], SYSTEM_PROMPT)
        self.assertEqual(config["allowed_tools"], list(TOOL_NAMES))
        self.assertTrue(config["strict_mcp_config"])
        self.assertEqual(config["setting_sources"], ["project"])
        self.assertEqual(config["tools"], [])

    def test_only_reduced_domain_tools_are_allowlisted(self) -> None:
        self.assertEqual(len(TOOL_NAMES), 6)
        self.assertTrue(all(name.startswith("mcp__bridal__") for name in TOOL_NAMES))


if __name__ == "__main__":
    unittest.main()
