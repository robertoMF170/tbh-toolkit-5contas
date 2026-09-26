import os
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tbh_discord as discord


class TestDiscordFarmAlerts(unittest.TestCase):
    def setUp(self):
        self.webhook = "https://discord.com/api/webhooks/123456789012345678/secret-token"
        self.user_id = "123456789012345678"

    def test_validates_webhook_and_user_id(self):
        self.assertTrue(discord.valid_webhook_url(self.webhook))
        self.assertFalse(discord.valid_webhook_url("http://discord.com/api/webhooks/123456789012345678/token"))
        self.assertFalse(discord.valid_webhook_url("https://discord.com.evil.example/api/webhooks/123456789012345678/token"))
        self.assertFalse(discord.valid_webhook_url("https://discord.com/api/webhooks/123456789012345678/token?wait=true"))
        self.assertTrue(discord.valid_discord_user_id(self.user_id))
        self.assertTrue(discord.valid_discord_user_id(f"<@{self.user_id}>"))
        self.assertFalse(discord.valid_discord_user_id("@robs"))
        self.assertFalse(discord.valid_discord_user_id("123"))

    def test_build_payload_pings_only_allowlisted_user(self):
        payload = discord.build_payload(
            {"name": "Mystic Gloves (Divine) A", "conta": "geek1781", "qtd": 1},
            f"<@{self.user_id}>",
        )
        self.assertIn(f"<@{self.user_id}>", payload["content"])
        self.assertIn("Mystic Gloves (Divine) A", payload["content"])
        self.assertEqual(payload["allowed_mentions"]["parse"], [])
        self.assertEqual(payload["allowed_mentions"]["users"], [self.user_id])

    def test_build_payload_formats_zone_alert_and_limits_mentions(self):
        payload = discord.build_payload({
            "type": "zone_status", "status": "incorrect", "item": "Shadow Bow",
            "conta": "Conta 1", "zone": "1-2 Normal", "expected": "1-1 Normal",
            "reason": "Verifica a fase atual.",
        }, f"<@{self.user_id}>")
        self.assertIn("ZONA INCORRETA", payload["content"])
        self.assertIn("Shadow Bow", payload["content"])
        self.assertIn("1-2 Normal", payload["content"])
        self.assertIn("1-1 Normal", payload["content"])
        self.assertEqual(payload["allowed_mentions"]["users"], [self.user_id])
        self.assertEqual(payload["allowed_mentions"]["parse"], [])

    def test_build_payload_formats_verify_and_correct_zone_statuses(self):
        for status, heading in (
            ("verify", "VERIFICA ZONA"),
            ("correct", "ZONA CORRETA"),
        ):
            with self.subTest(status=status):
                payload = discord.build_payload({
                    "type": "zone_status", "status": status, "item": "Item",
                    "conta": "Conta", "zone": "1-1 Normal",
                })
                self.assertIn(heading, payload["content"])

    def test_build_payload_does_not_ping_handle_or_everyone(self):
        payload = discord.build_payload(
            {"name": "Item", "conta": "geek1781", "qtd": 1},
            "@robs",
        )
        self.assertNotIn("@robs", payload["content"])
        self.assertNotIn("@everyone", payload["content"])
        self.assertEqual(payload["allowed_mentions"]["users"], [])
        self.assertEqual(payload["allowed_mentions"]["parse"], [])

    def test_save_settings_preserves_other_values_and_reads_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = os.path.join(tmp, ".env")
            with open(env_file, "w", encoding="utf-8") as fh:
                fh.write("KEEP_ME=value\nTBH_DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/123456789012345678/old-token\n")
            discord.save_discord_settings(self.webhook, self.user_id, env_file)
            loaded = discord.discord_settings(env_file)
            self.assertEqual(loaded, (self.webhook, self.user_id))
            with open(env_file, encoding="utf-8") as fh:
                content = fh.read()
            self.assertIn("KEEP_ME=value", content)
            self.assertIn("TBH_DISCORD_MENTION_ID=" + self.user_id, content)
            self.assertNotIn("old-token", content)

    def test_save_rejects_handle_and_bad_webhook_without_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = os.path.join(tmp, ".env")
            with open(env_file, "w", encoding="utf-8") as fh:
                fh.write("KEEP_ME=value\n")
            with self.assertRaises(ValueError):
                discord.save_discord_settings(self.webhook, "@robs", env_file)
            with self.assertRaises(ValueError):
                discord.save_discord_settings("https://example.com/hook", self.user_id, env_file)
            with open(env_file, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "KEEP_ME=value\n")

    def test_discord_desligado_por_predefinicao_ate_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            enabled_file = os.path.join(tmp, "enabled")
            self.assertFalse(discord.discord_enabled(enabled_file))
            discord.set_discord_enabled(True, enabled_file)
            self.assertTrue(discord.discord_enabled(enabled_file))
            discord.set_discord_enabled(False, enabled_file)
            self.assertFalse(discord.discord_enabled(enabled_file))

    def test_escolha_guardada_tem_precedencia_sobre_variavel_de_ambiente(self):
        with tempfile.TemporaryDirectory() as tmp:
            enabled_file = os.path.join(tmp, "enabled")
            with mock.patch.dict(os.environ, {"TBH_DISCORD_ENABLED": "1"}):
                self.assertTrue(discord.discord_enabled(enabled_file))
                discord.set_discord_enabled(False, enabled_file)
                self.assertFalse(discord.discord_enabled(enabled_file))
                discord.set_discord_enabled(True, enabled_file)
                self.assertTrue(discord.discord_enabled(enabled_file))

    def test_send_alert_posts_payload_and_never_logs_url(self):
        calls = []
        output = []

        def transport(url, payload, timeout):
            calls.append((url, payload, timeout))
            return 204

        with (
            mock.patch.object(discord, "discord_settings", return_value=(self.webhook, self.user_id)),
            mock.patch("builtins.print", side_effect=lambda *args, **kwargs: output.append(str(args[0]))),
        ):
            sent = discord.send_alert(
                {"name": "Mystic Gloves (Divine) A", "conta": "Conta 1 (geek1781)", "qtd": 1},
                transport=transport,
                sleep=lambda _delay: None,
            )

        self.assertTrue(sent)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], self.webhook)
        self.assertIn("Mystic Gloves (Divine) A", calls[0][1]["content"])
        self.assertTrue(all(self.webhook not in line for line in output))

    def test_send_alert_retries_rate_limit_then_succeeds(self):
        statuses = [429, 204]
        calls = []

        def transport(url, payload, timeout):
            calls.append(url)
            return statuses.pop(0)

        delays = []
        with mock.patch.object(discord, "discord_settings", return_value=(self.webhook, "")):
            sent = discord.send_alert(
                {"name": "Item", "conta": "Conta", "qtd": 1},
                transport=transport,
                sleep=delays.append,
            )

        self.assertTrue(sent)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(delays), 1)

    def test_send_alert_no_config_does_not_request(self):
        transport = mock.Mock()
        with mock.patch.object(discord, "discord_settings", return_value=("", "")):
            sent = discord.send_alert({"name": "Item"}, transport=transport, sleep=lambda _delay: None)
        self.assertFalse(sent)
        transport.assert_not_called()

    def test_send_alert_timeout_is_not_retried_to_avoid_duplicate_ping(self):
        transport = mock.Mock(side_effect=urllib.error.URLError("offline"))
        with mock.patch.object(discord, "discord_settings", return_value=(self.webhook, "")):
            sent = discord.send_alert(
                {"name": "Item"}, transport=transport, sleep=lambda _delay: None
            )
        self.assertFalse(sent)
        transport.assert_called_once()


if __name__ == "__main__":
    unittest.main()
