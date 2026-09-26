import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from collections import Counter
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tbh_farm_alert as alert


class FakeInventory:
    def carregar_dados_jogo(self):
        return {"gear": {}, "nomes": {}}

    def itens_da_conta_detalhado(self, save_path, game_data, market_names):
        if save_path == "broken":
            raise OSError("save temporariamente bloqueado")
        items = json.loads(save_path)
        return Counter(items), Counter()


def write_json(path, value):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(value, fh)


class FarmAlertTestCase(unittest.TestCase):
    def setUp(self):
        # Polling may emit zone alerts by default; never let unit tests contact a real webhook.
        sender_patch = mock.patch.object(alert.tbh_discord, "send_alert")
        sender_patch.start()
        self.addCleanup(sender_patch.stop)


class TestAlertData(FarmAlertTestCase):
    def test_notify_drop_envia_discord_sem_impedir_alerta_local(self):
        hit = {"name": "Mystic Gloves (Divine) A", "conta": "Conta 1 (geek1781)", "qtd": 1}
        with (
            mock.patch.object(alert.tbh_discord, "send_alert") as send,
            mock.patch.object(alert.os, "name", "posix"),
            redirect_stdout(io.StringIO()),
        ):
            alert.notify_drop(hit)
        send.assert_called_once_with(hit)

    def test_teste_discord_aceita_confirmacao_em_minusculas(self):
        webhook = "https://discord.com/api/webhooks/123456789012345678/test-token"
        output = io.StringIO()
        with (
            mock.patch.object(alert.tbh_discord, "discord_settings", return_value=(webhook, "1406003990063480922")),
            mock.patch.object(alert.tbh_discord, "send_alert", return_value=True) as send,
            mock.patch("builtins.input", return_value="sim"),
            redirect_stdout(output),
        ):
            result = alert.main(["--test-discord"])
        self.assertEqual(result, 0)
        send.assert_called_once_with(
            {"name": "Teste do alerta de farm", "conta": "teste manual", "qtd": 1},
            test=True,
        )

    def test_prompt_discord_nao_desativa_webhook_guardado(self):
        output = io.StringIO()
        with (
            mock.patch.object(alert.tbh_discord, "discord_settings", return_value=("", "")),
            mock.patch.object(alert.tbh_discord, "set_discord_enabled") as set_enabled,
            mock.patch.object(alert, "_ask_yes_no", return_value=False),
            redirect_stdout(output),
        ):
            result = alert.main(["--discord-prompt"])
        self.assertEqual(result, 0)
        set_enabled.assert_called_once_with(False)
        self.assertIn("vigia local continua ativa", output.getvalue())

    def test_prompt_discord_configurado_ativa_sem_enviar_teste(self):
        webhook = "https://discord.com/api/webhooks/123456789012345678/test-token"
        output = io.StringIO()
        with (
            mock.patch.object(alert.tbh_discord, "discord_settings", return_value=(webhook, "")),
            mock.patch.object(alert.tbh_discord, "set_discord_enabled") as set_enabled,
            mock.patch.object(alert.tbh_discord, "send_alert") as send,
            mock.patch.object(alert, "_ask_yes_no", return_value=True),
            redirect_stdout(output),
        ):
            result = alert.main(["--discord-prompt"])
        self.assertEqual(result, 0)
        set_enabled.assert_called_once_with(True)
        send.assert_not_called()

    def test_prompt_discord_sem_config_permite_seguir_sem_configurar(self):
        output = io.StringIO()
        with (
            mock.patch.object(alert.tbh_discord, "discord_settings", return_value=("", "")),
            mock.patch.object(alert.tbh_discord, "set_discord_enabled") as set_enabled,
            mock.patch.object(alert, "_ask_yes_no", side_effect=[True, False]) as ask,
            redirect_stdout(output),
        ):
            result = alert.main(["--discord-prompt"])
        self.assertEqual(result, 0)
        set_enabled.assert_called_once_with(False)
        ask.assert_any_call("Queres configurar agora? [S/N]: ")
        self.assertIn("Para receber alertas no canal", output.getvalue())

    def test_teste_discord_continua_a_exigir_confirmacao(self):
        webhook = "https://discord.com/api/webhooks/123456789012345678/test-token"
        output = io.StringIO()
        with (
            mock.patch.object(alert.tbh_discord, "discord_settings", return_value=(webhook, "")),
            mock.patch.object(alert.tbh_discord, "send_alert") as send,
            mock.patch("builtins.input", return_value="nao"),
            redirect_stdout(output),
        ):
            result = alert.main(["--test-discord"])
        self.assertEqual(result, 3)
        self.assertIn("Teste Discord cancelado.", output.getvalue())
        send.assert_not_called()

    def test_resolve_conta_por_nome_e_alias_steam(self):
        accounts = [
            {"name": "Conta 1 (geek1781)"},
            {"name": "Conta 2 (opiratanumero1)"},
        ]
        self.assertEqual(alert.resolve_account_name("Conta 1 (geek1781)", accounts), "Conta 1 (geek1781)")
        self.assertEqual(alert.resolve_account_name("geek1781", accounts), "Conta 1 (geek1781)")
        self.assertIsNone(alert.resolve_account_name("nao-existe", accounts))

    def test_status_confirma_alvo_na_conta_pelo_alias_steam(self):
        heartbeat = {
            "alive": True,
            "age_seconds": 1,
            "accounts": ["Conta 1 (geek1781)"],
            "watched_accounts": ["Conta 1 (geek1781)"],
            "targets": [{"name": "Shadow Bow", "conta": "geek1781"}],
            "target_count": 1,
            "account_count": 1,
            "status": "active",
            "updated_at": "agora",
            "interval_seconds": 2,
            "unreadable_accounts": [],
        }
        output = io.StringIO()
        with (
            mock.patch.object(alert, "watcher_status", return_value=heartbeat),
            mock.patch.object(alert, "_watch_process_running", return_value=True),
            mock.patch.object(alert, "_print_watch_summary") as print_summary,
            redirect_stdout(output),
        ):
            result = alert.main(["--status", "--once", "--conta", "geek1781"])
        self.assertEqual(result, 0)
        self.assertIn("VIGIA ATIVO", output.getvalue())
        self.assertIn("Contas vigiadas: Conta 1 (geek1781)", output.getvalue())
        self.assertIn("geek1781 -> Conta 1 (geek1781)", output.getvalue())
        print_summary.assert_called_once_with(
            [{"name": "Shadow Bow", "conta": "geek1781"}],
            [{"name": "Conta 1 (geek1781)"}],
        )

    def test_status_por_padrao_fica_em_loop_e_atualiza_sem_limpar(self):
        heartbeat = {
            "alive": True,
            "age_seconds": 1,
            "accounts": ["Conta 1"],
            "watched_accounts": ["Conta 1"],
            "targets": [{"name": "Shadow Bow", "conta": ""}],
            "target_count": 1,
            "status": "active",
            "updated_at": "2026-04-01T12:00:00",
            "interval_seconds": 2,
            "unreadable_accounts": [],
        }
        output = io.StringIO()
        with (
            mock.patch.object(alert, "watcher_status", return_value=heartbeat) as get_status,
            mock.patch.object(alert, "_watch_process_running", return_value=True),
            mock.patch.object(alert, "_print_watch_summary"),
            mock.patch.object(alert, "_matching_target_hits", return_value=[]),
            mock.patch.object(alert, "_watch_data", return_value={"targets": [], "hits": []}),
            mock.patch.object(alert.tbh_discord, "discord_settings", return_value=("", "")),
            mock.patch.object(alert.time, "sleep", side_effect=[None, KeyboardInterrupt]) as sleep,
            redirect_stdout(output),
        ):
            result = alert.main(["--status", "--status-interval", "5"])

        text = output.getvalue()
        self.assertEqual(result, 0)
        self.assertEqual(get_status.call_count, 2)
        self.assertEqual(sleep.call_args_list, [mock.call(5.0), mock.call(5.0)])
        self.assertIn("sem limpar o ecrã", text)
        self.assertIn("VIGIA ATIVO", text)
        self.assertIn("ATIVA A VIGIAR", text)
        self.assertIn("2026-04-01T12:00:00", text)
        self.assertNotIn("\x1b[2J", text)
        self.assertIn("Acompanhamento do status parado", text)

    def test_status_loop_avisa_quando_deteta_novo_drop(self):
        hit = {"name": "Shadow Bow", "conta": "Conta 1", "qtd": 1, "time": "2026-04-01T12:01:00"}
        output = io.StringIO()
        with (
            mock.patch.object(alert, "_status_report", return_value=0),
            mock.patch.object(alert, "_watch_data", side_effect=[
                {"hits": []},
                {"hits": [hit]},
            ]),
            mock.patch.object(alert.time, "sleep", side_effect=KeyboardInterrupt),
            redirect_stdout(output),
        ):
            result = alert.main(["--status", "--status-interval", "5"])

        self.assertEqual(result, 0)
        self.assertIn("NOVO DROP DETETADO — Shadow Bow", output.getvalue())
        self.assertIn("Conta: Conta 1 | +1 | 2026-04-01T12:01:00", output.getvalue())

    def test_resumo_mostra_unidades_encontradas_por_alvo(self):
        with tempfile.TemporaryDirectory() as tmp:
            watch = os.path.join(tmp, "farm_watch.json")
            write_json(watch, {"targets": [], "hits": [
                {"name": "Shadow Bow", "conta": "Conta 1 (geek1781)", "qtd": 2},
                {"name": "Shadow Bow", "conta": "Conta 1 (geek1781)", "qtd": 1, "acknowledged": True},
                {"name": "Shadow Bow", "conta": "Conta 2 (other)", "qtd": 5},
            ]})
            output = io.StringIO()
            with redirect_stdout(output):
                alert._print_watch_summary(
                    [{"name": "Shadow Bow", "conta": "geek1781"}],
                    [{"name": "Conta 1 (geek1781)"}, {"name": "Conta 2 (other)"}],
                    watch,
                )
        self.assertIn("Alvos a vigiar (1)", output.getvalue())
        self.assertIn("Shadow Bow @ geek1781 — 3 unidades encontradas em 2 alertas.", output.getvalue())
        self.assertIn("Total nos últimos 100 registos guardados: 3 unidades em 2 alertas.", output.getvalue())

    def test_conta_explicita_restringe_a_leitura_a_conta_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            watch = os.path.join(tmp, "watch.json")
            accounts = os.path.join(tmp, "accounts.json")
            state = os.path.join(tmp, "state.json")
            prices = os.path.join(tmp, "prices.json")
            write_json(watch, {"targets": [{"name": "Shadow Bow", "conta": "geek1781"}], "hits": []})
            write_json(accounts, {"contas": [
                {"nome": "Conta 1 (geek1781)", "save": "save-1"},
                {"nome": "Conta 2 (other)", "save": "save-2"},
            ]})
            write_json(prices, {"itens": {"Shadow Bow": {"sell": 1}}})
            inventory = mock.Mock()
            inventory.carregar_dados_jogo.return_value = {"gear": {}, "nomes": {}}
            inventory.itens_da_conta_detalhado.side_effect = [
                (Counter({"Shadow Bow": 0}), Counter()),
            ]
            with (
                mock.patch.object(alert, "_GAME_DATA_CACHE", None),
                mock.patch.object(alert, "_GAME_DATA_OWNER", None),
                mock.patch.object(alert, "_LAST_SCAN_ERRORS", {}),
            ):
                self.assertEqual(alert.poll_once(state, watch, accounts, prices, inventory, lambda hit: None), [])
            inventory.itens_da_conta_detalhado.assert_called_once_with(
                "save-1", inventory.carregar_dados_jogo.return_value, {"Shadow Bow"},
            )

    def test_scan_dados_jogo_falhados_devolve_conta_como_nao_legivel(self):
        class MissingGameData:
            def carregar_dados_jogo(self):
                raise SystemExit("ficheiros tbhdata em falta")

        with (
            mock.patch.object(alert, "_GAME_DATA_CACHE", None),
            mock.patch.object(alert, "_GAME_DATA_OWNER", None),
            mock.patch.object(alert, "_LAST_SCAN_ERRORS", {}),
        ):
            snapshots, failed = alert.scan_inventories(
                [{"name": "Conta 1 (geek1781)", "save": "save.es3"}],
                {"Shadow Bow"},
                MissingGameData(),
            )
        self.assertEqual(snapshots, {})
        self.assertEqual(failed, {"Conta 1 (geek1781)"})

    def test_estado_status_do_heartbeat_ativo_ou_expirado(self):
        with tempfile.TemporaryDirectory() as tmp:
            heartbeat = os.path.join(tmp, "heartbeat.json")
            write_json(heartbeat, {"updated_epoch": 100.0, "status": "active"})
            ativo = alert.watcher_status(heartbeat, now=103, interval=2)
            expirado = alert.watcher_status(heartbeat, now=120, interval=2)
        self.assertTrue(ativo["alive"])
        self.assertEqual(ativo["status"], "active")
        self.assertFalse(expirado["alive"])

    def test_check_running_confirma_lock_sem_heartbeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = os.path.join(tmp, "watch.lock")
            owner = alert._acquire_watch_lock(lock)
            self.assertIsNotNone(owner)
            try:
                with mock.patch.object(alert, "LOCK_FILE", lock), mock.patch.object(alert, "HEARTBEAT_FILE", os.path.join(tmp, "no-heartbeat.json")):
                    output = io.StringIO()
                    with redirect_stdout(output):
                        result = alert.main(["--check-running"])
                self.assertEqual(result, 0)
                self.assertIn("VIGIA JA EM EXECUCAO", output.getvalue())
            finally:
                alert._release_watch_lock(owner)

    def test_lock_do_vigia_e_exclusivo_e_libertado(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = os.path.join(tmp, "watch.lock")
            owner = alert._acquire_watch_lock(lock)
            self.assertIsNotNone(owner)
            try:
                self.assertTrue(alert._watch_process_running(lock))
            finally:
                alert._release_watch_lock(owner)
            self.assertFalse(alert._watch_process_running(lock))

    def test_snapshot_falhado_nao_reutiliza_baseline_antiga_de_outra_conta(self):
        with tempfile.TemporaryDirectory() as tmp:
            watch = os.path.join(tmp, "watch.json")
            accounts = os.path.join(tmp, "accounts.json")
            state = os.path.join(tmp, "state.json")
            prices = os.path.join(tmp, "prices.json")
            write_json(watch, {"targets": [], "hits": []})
            write_json(accounts, {"contas": [{
                "nome": "Conta 1 (geek1781)", "save": "broken"
            }]})
            write_json(prices, {"itens": {"Shadow Bow": {"sell": 1}}})
            write_json(state, {
                "accounts": {"Conta 1 (geek1781)": {"Shadow Bow": 4}},
                "target_baselines": {},
            })
            with (
                mock.patch.object(alert, "_GAME_DATA_CACHE", None),
                mock.patch.object(alert, "_GAME_DATA_OWNER", None),
                mock.patch.object(alert, "_LAST_SCAN_ERRORS", {}),
            ):
                self.assertTrue(alert.add_target(
                    "Shadow Bow", "geek1781", watch,
                    state_file=state, accounts_file=accounts,
                    price_file=prices, inventory=FakeInventory(),
                ))
            key = alert._target_key({"name": "Shadow Bow", "conta": "geek1781"})
            self.assertEqual(alert._read_json(state, {})["target_baselines"][key]["accounts"], {})

    def test_adiciona_remove_e_confirma_alvos_e_hits(self):
        with tempfile.TemporaryDirectory() as tmp:
            watch = os.path.join(tmp, "farm_watch.json")
            self.assertTrue(alert.add_target("Shadow Bow", "Conta 1", watch, state_file=os.path.join(tmp, "state.json"), accounts_file=os.path.join(tmp, "accounts.json")))
            self.assertFalse(alert.add_target("shadow bow", "conta 1", watch, state_file=os.path.join(tmp, "state.json"), accounts_file=os.path.join(tmp, "accounts.json")))
            self.assertEqual(alert.load_targets(watch), [{"name": "Shadow Bow", "conta": "Conta 1"}])
            alert._record_hit({"name": "Shadow Bow", "conta": "Conta 1", "qtd": 1}, watch)
            self.assertEqual(alert.acknowledge_hits("Shadow Bow", watch_file=watch), 1)
            self.assertTrue(alert.remove_target("Shadow Bow", "Conta 1", watch))
            data = alert._read_json(watch, {})
            self.assertEqual(data["targets"], [])
            self.assertTrue(data["hits"][0]["acknowledged"])

    def test_clique_farm_inicializa_com_quantidade_atual_sem_alerta_falso(self):
        with tempfile.TemporaryDirectory() as tmp:
            watch = os.path.join(tmp, "watch.json")
            accounts = os.path.join(tmp, "accounts.json")
            state = os.path.join(tmp, "state.json")
            prices = os.path.join(tmp, "prices.json")
            write_json(watch, {"targets": [], "hits": []})
            write_json(accounts, {"contas": [{"nome": "Conta 1 (geek1781)", "save": json.dumps({"Shadow Bow": 4})}]})
            write_json(prices, {"itens": {"Shadow Bow": {"sell": 1}}})
            with mock.patch.object(alert, "_GAME_DATA_CACHE", None):
                self.assertTrue(alert.add_target("Shadow Bow", "geek1781", watch, state_file=state, accounts_file=accounts, price_file=prices, inventory=FakeInventory()))
                notified = []
                self.assertEqual(alert.poll_once(
                    state, watch, accounts, prices, FakeInventory(), notified.append,
                    zone_reader=lambda _save: {}, notify_zone=lambda _alert: None,
                ), [])
                self.assertEqual(notified, [])
                key = alert._target_key({"name": "Shadow Bow", "conta": "geek1781"})
                self.assertEqual(alert._read_json(state, {})["target_baselines"][key]["accounts"]["conta 1 (geek1781)"], 4)
                write_json(accounts, {"contas": [{"nome": "Conta 1 (geek1781)", "save": json.dumps({"Shadow Bow": 5})}]})
                hits = alert.poll_once(
                    state, watch, accounts, prices, FakeInventory(), notified.append,
                    zone_reader=lambda _save: {}, notify_zone=lambda _alert: None,
                )
            self.assertEqual(hits, [{"name": "Shadow Bow", "conta": "Conta 1 (geek1781)", "qtd": 1}])
            self.assertEqual(notified, hits)

    def test_save_indisponivel_ao_registar_nao_gera_drop_falso_ao_recuperar(self):
        with tempfile.TemporaryDirectory() as tmp:
            watch = os.path.join(tmp, "watch.json")
            accounts = os.path.join(tmp, "accounts.json")
            state = os.path.join(tmp, "state.json")
            prices = os.path.join(tmp, "prices.json")
            write_json(watch, {"targets": [], "hits": []})
            write_json(accounts, {"contas": [{"nome": "Conta 1 (geek1781)", "save": "broken"}]})
            write_json(prices, {"itens": {"Shadow Bow": {"sell": 1}}})
            inventory = FakeInventory()
            with (
                mock.patch.object(alert, "_GAME_DATA_CACHE", None),
                mock.patch.object(alert, "_GAME_DATA_OWNER", None),
                mock.patch.object(alert, "_LAST_SCAN_ERRORS", {}),
            ):
                self.assertTrue(alert.add_target(
                    "Shadow Bow", "geek1781", watch,
                    state_file=state, accounts_file=accounts,
                    price_file=prices, inventory=inventory,
                ))
                key = alert._target_key({"name": "Shadow Bow", "conta": "geek1781"})
                self.assertEqual(alert._read_json(state, {})["target_baselines"][key]["accounts"], {})
                # O save fica legivel depois do clique, mas o item já existia.
                write_json(accounts, {"contas": [{
                    "nome": "Conta 1 (geek1781)", "save": json.dumps({"Shadow Bow": 4})
                }]})
                self.assertEqual(alert.poll_once(
                    state, watch, accounts, prices, inventory,
                    lambda hit: self.fail("nao deve avisar ao definir a primeira linha de base"),
                    zone_reader=lambda _save: {}, notify_zone=lambda _alert: None,
                ), [])
                write_json(accounts, {"contas": [{
                    "nome": "Conta 1 (geek1781)", "save": json.dumps({"Shadow Bow": 5})
                }]})
                hits = alert.poll_once(
                    state, watch, accounts, prices, inventory, lambda hit: None,
                    zone_reader=lambda _save: {}, notify_zone=lambda _alert: None,
                )
        self.assertEqual(hits, [{"name": "Shadow Bow", "conta": "Conta 1 (geek1781)", "qtd": 1}])

    def test_linha_de_base_nao_avisa_por_item_que_ja_tinha(self):
        with tempfile.TemporaryDirectory() as tmp:
            watch = os.path.join(tmp, "watch.json")
            accounts = os.path.join(tmp, "accounts.json")
            state = os.path.join(tmp, "state.json")
            prices = os.path.join(tmp, "prices.json")
            write_json(watch, {"targets": [{"name": "Shadow Bow", "conta": "Conta 1"}], "hits": []})
            write_json(accounts, {"contas": [{"nome": "Conta 1", "save": json.dumps({"Shadow Bow": 4})}]})
            write_json(prices, {"itens": {"Shadow Bow": {"sell": 1}}})
            with mock.patch.object(alert, "_GAME_DATA_CACHE", None):
                self.assertEqual(alert.poll_once(
                    state, watch, accounts, prices, FakeInventory(), lambda hit: self.fail("false alarm"),
                    zone_reader=lambda _save: {}, notify_zone=lambda _alert: None,
                ), [])
                self.assertEqual(alert.poll_once(
                    state, watch, accounts, prices, FakeInventory(), lambda hit: self.fail("false alarm"),
                    zone_reader=lambda _save: {}, notify_zone=lambda _alert: None,
                ), [])

    def test_avisa_um_novo_drop_e_nao_repete_depois(self):
        with tempfile.TemporaryDirectory() as tmp:
            watch = os.path.join(tmp, "watch.json")
            accounts = os.path.join(tmp, "accounts.json")
            state = os.path.join(tmp, "state.json")
            prices = os.path.join(tmp, "prices.json")
            write_json(watch, {"targets": [{"name": "Shadow Bow", "conta": "Conta 1"}], "hits": []})
            write_json(accounts, {"contas": [{"nome": "Conta 1", "save": json.dumps({"Shadow Bow": 0})}]})
            write_json(prices, {"itens": {"Shadow Bow": {"sell": 1}}})
            with mock.patch.object(alert, "_GAME_DATA_CACHE", None):
                alert.poll_once(
                    state, watch, accounts, prices, FakeInventory(), lambda hit: self.fail("false alarm"),
                    zone_reader=lambda _save: {}, notify_zone=lambda _alert: None,
                )
                write_json(accounts, {"contas": [{"nome": "Conta 1", "save": json.dumps({"Shadow Bow": 1})}]})
                notified = []
                hits = alert.poll_once(
                    state, watch, accounts, prices, FakeInventory(), notified.append,
                    zone_reader=lambda _save: {}, notify_zone=lambda _alert: None,
                )
                self.assertEqual(hits, [{"name": "Shadow Bow", "conta": "Conta 1", "qtd": 1}])
                self.assertEqual(notified, hits)
                self.assertEqual(alert.poll_once(
                    state, watch, accounts, prices, FakeInventory(), lambda hit: self.fail("duplicate alarm"),
                    zone_reader=lambda _save: {}, notify_zone=lambda _alert: None,
                ), [])
            data = alert._read_json(watch, {})
            self.assertEqual(len(data["hits"]), 1)
            self.assertEqual(data["hits"][0]["conta"], "Conta 1")

    def test_sem_conta_deteccao_auto_encontra_a_conta_certa(self):
        with tempfile.TemporaryDirectory() as tmp:
            watch = os.path.join(tmp, "watch.json")
            accounts = os.path.join(tmp, "accounts.json")
            state = os.path.join(tmp, "state.json")
            prices = os.path.join(tmp, "prices.json")
            write_json(watch, {"targets": [{"name": "Shadow Bow", "conta": ""}], "hits": []})
            write_json(accounts, {"contas": [
                {"nome": "Conta 1", "save": json.dumps({"Shadow Bow": 0})},
                {"nome": "Conta 2", "save": json.dumps({"Shadow Bow": 8})},
            ]})
            write_json(prices, {"itens": {"Shadow Bow": {"sell": 1}}})
            with mock.patch.object(alert, "_GAME_DATA_CACHE", None):
                alert.poll_once(
                    state, watch, accounts, prices, FakeInventory(), lambda hit: self.fail("false alarm"),
                    zone_reader=lambda _save: {}, notify_zone=lambda _alert: None,
                )
                write_json(accounts, {"contas": [
                    {"nome": "Conta 1", "save": json.dumps({"Shadow Bow": 0})},
                    {"nome": "Conta 2", "save": json.dumps({"Shadow Bow": 9})},
                ]})
                hits = alert.poll_once(
                    state, watch, accounts, prices, FakeInventory(), lambda hit: None,
                    zone_reader=lambda _save: {}, notify_zone=lambda _alert: None,
                )
            self.assertEqual(hits, [{"name": "Shadow Bow", "conta": "Conta 2", "qtd": 1}])

    def test_save_com_falha_preserva_ultima_leitura_sem_alarme(self):
        with tempfile.TemporaryDirectory() as tmp:
            watch = os.path.join(tmp, "watch.json")
            accounts = os.path.join(tmp, "accounts.json")
            state = os.path.join(tmp, "state.json")
            prices = os.path.join(tmp, "prices.json")
            write_json(watch, {"targets": [{"name": "Shadow Bow", "conta": "Conta 1"}], "hits": []})
            write_json(accounts, {"contas": [{"nome": "Conta 1", "save": json.dumps({"Shadow Bow": 2})}]})
            write_json(prices, {"itens": {"Shadow Bow": {"sell": 1}}})
            with mock.patch.object(alert, "_GAME_DATA_CACHE", None):
                alert.poll_once(
                    state, watch, accounts, prices, FakeInventory(), lambda hit: self.fail("false alarm"),
                    zone_reader=lambda _save: {}, notify_zone=lambda _alert: None,
                )
                write_json(accounts, {"contas": [{"nome": "Conta 1", "save": "broken"}]})
                self.assertEqual(alert.poll_once(
                    state, watch, accounts, prices, FakeInventory(), lambda hit: self.fail("false alarm"),
                    zone_reader=lambda _save: {}, notify_zone=lambda _alert: None,
                ), [])
            self.assertEqual(alert._read_json(state, {})["accounts"]["Conta 1"]["Shadow Bow"], 2)

    def test_nova_conta_tem_linha_de_base_sem_alerta_falso(self):
        with tempfile.TemporaryDirectory() as tmp:
            watch = os.path.join(tmp, "watch.json")
            accounts = os.path.join(tmp, "accounts.json")
            state = os.path.join(tmp, "state.json")
            prices = os.path.join(tmp, "prices.json")
            write_json(watch, {"targets": [{"name": "Shadow Bow", "conta": ""}], "hits": []})
            write_json(accounts, {"contas": [{"nome": "Conta 1", "save": json.dumps({"Shadow Bow": 1})}]})
            write_json(prices, {"itens": {"Shadow Bow": {"sell": 1}}})
            with mock.patch.object(alert, "_GAME_DATA_CACHE", None):
                alert.poll_once(
                    state, watch, accounts, prices, FakeInventory(), lambda hit: self.fail("false alarm"),
                    zone_reader=lambda _save: {}, notify_zone=lambda _alert: None,
                )
                write_json(accounts, {"contas": [
                    {"nome": "Conta 1", "save": json.dumps({"Shadow Bow": 1})},
                    {"nome": "Conta 2", "save": json.dumps({"Shadow Bow": 5})},
                ]})
                self.assertEqual(alert.poll_once(
                    state, watch, accounts, prices, FakeInventory(), lambda hit: self.fail("new account false alarm"),
                    zone_reader=lambda _save: {}, notify_zone=lambda _alert: None,
                ), [])
                write_json(accounts, {"contas": [
                    {"nome": "Conta 1", "save": json.dumps({"Shadow Bow": 1})},
                    {"nome": "Conta 2", "save": json.dumps({"Shadow Bow": 6})},
                ]})
                hits = alert.poll_once(
                    state, watch, accounts, prices, FakeInventory(), lambda hit: None,
                    zone_reader=lambda _save: {}, notify_zone=lambda _alert: None,
                )
            self.assertEqual(hits, [{"name": "Shadow Bow", "conta": "Conta 2", "qtd": 1}])

    def test_find_new_drops_respeita_a_conta_do_alvo(self):
        previous = {"Conta 1": {"Shadow Bow": 1}, "Conta 2": {"Shadow Bow": 1}}
        current = {"Conta 1": {"Shadow Bow": 1}, "Conta 2": {"Shadow Bow": 2}}
        targets = [{"name": "Shadow Bow", "conta": "Conta 1"}]
        self.assertEqual(alert.find_new_drops(previous, current, targets), [])


class TestFarmZoneValidation(FarmAlertTestCase):
    NORMAL_DROP = [[1, 1, 10, 0, "", 0, 0, 0, 0, 0]]
    TORMENT_DROP = [[1, 1, 90, 3, "", 0, 0, 0, 0, 0]]

    def test_classifica_zona_correta_incorreta_e_sem_dados(self):
        correct, _, _ = alert._evaluate_zone(
            {"act": 1, "no": 1, "diff_index": 0, "plague": False},
            self.NORMAL_DROP,
        )
        incorrect, _, _ = alert._evaluate_zone(
            {"act": 1, "no": 2, "diff_index": 0, "plague": False},
            self.NORMAL_DROP,
        )
        unknown_save, _, _ = alert._evaluate_zone({}, self.NORMAL_DROP)
        unknown_item, _, _ = alert._evaluate_zone(
            {"act": 1, "no": 1, "diff_index": 0, "plague": False}, [],
        )
        self.assertEqual(correct, "correct")
        self.assertEqual(incorrect, "incorrect")
        self.assertEqual(unknown_save, "verify")
        self.assertEqual(unknown_item, "verify")

    def test_scan_devolve_zona_junto_com_inventario(self):
        class CombinedInventory(FakeInventory):
            def itens_da_conta_com_zona(self, save_path, game_data, market_names):
                items, deleted = self.itens_da_conta_detalhado(save_path, game_data, market_names)
                return items, deleted, {"key": 1101, "act": 1, "no": 1, "label": "1-1 Normal"}

        zones = {}
        with (
            mock.patch.object(alert, "_GAME_DATA_CACHE", None),
            mock.patch.object(alert, "_GAME_DATA_OWNER", None),
            mock.patch.object(alert, "_LAST_SCAN_ERRORS", {}),
        ):
            snapshots, failed = alert.scan_inventories(
                [{"name": "Conta 1", "save": json.dumps({"Shadow Bow": 2})}],
                {"Shadow Bow"}, CombinedInventory(), zone_snapshots=zones,
            )
        self.assertEqual(snapshots, {"Conta 1": {"Shadow Bow": 2}})
        self.assertEqual(failed, set())
        self.assertEqual(zones["Conta 1"]["key"], 1101)

    def test_save_ilegivel_notifica_verifica_zona_so_uma_vez(self):
        with tempfile.TemporaryDirectory() as tmp:
            watch = os.path.join(tmp, "watch.json")
            accounts = os.path.join(tmp, "accounts.json")
            state = os.path.join(tmp, "state.json")
            prices = os.path.join(tmp, "prices.json")
            write_json(watch, {"targets": [{"name": "Shadow Bow", "conta": ""}], "hits": []})
            write_json(accounts, {"contas": [{"nome": "Conta 1", "save": "broken"}]})
            write_json(prices, {"itens": {"Shadow Bow": {"sell": 1}}})
            zone_alerts = []
            with (
                mock.patch.object(alert.tbh_discord, "send_alert"),
                mock.patch.object(alert, "_GAME_DATA_CACHE", None),
                mock.patch.object(alert, "_GAME_DATA_OWNER", None),
                mock.patch.object(alert, "_LAST_SCAN_ERRORS", {}),
                mock.patch.object(alert, "_drop_stages_for_name", return_value=self.NORMAL_DROP),
            ):
                for _ in range(2):
                    alert.poll_once(
                        state, watch, accounts, prices, FakeInventory(), lambda _hit: None,
                        zone_reader=lambda _save: {},
                        notify_zone=zone_alerts.append,
                    )
            self.assertEqual([item["status"] for item in zone_alerts], ["verify"])
            self.assertIn("zone_unreadable", alert._read_json(state, {}))

    def test_poll_notifica_status_inicial_e_so_repete_ao_mudar_classificacao(self):
        with tempfile.TemporaryDirectory() as tmp:
            watch = os.path.join(tmp, "watch.json")
            accounts = os.path.join(tmp, "accounts.json")
            state = os.path.join(tmp, "state.json")
            prices = os.path.join(tmp, "prices.json")
            write_json(watch, {"targets": [{"name": "Shadow Bow", "conta": ""}], "hits": []})
            write_json(accounts, {"contas": [{
                "nome": "Conta 1", "save": json.dumps({"Shadow Bow": 0}),
            }]})
            write_json(prices, {"itens": {"Shadow Bow": {"sell": 1}}})
            zone = {"key": 1101, "act": 1, "no": 1, "diff": "NORMAL",
                    "diff_index": 0, "plague": False, "label": "1-1 Normal"}
            zone_alerts = []
            inventory = FakeInventory()
            with (
                mock.patch.object(alert, "_GAME_DATA_CACHE", None),
                mock.patch.object(alert, "_GAME_DATA_OWNER", None),
                mock.patch.object(alert, "_LAST_SCAN_ERRORS", {}),
                mock.patch.object(alert, "_drop_stages_for_name", return_value=self.NORMAL_DROP),
            ):
                for _ in range(2):
                    alert.poll_once(
                        state, watch, accounts, prices, inventory, lambda _hit: None,
                        zone_reader=lambda _save: zone,
                        notify_zone=zone_alerts.append,
                    )
                self.assertEqual([item["status"] for item in zone_alerts], ["correct"])

                zone.update({"key": 1102, "no": 2, "label": "1-2 Normal"})
                alert.poll_once(
                    state, watch, accounts, prices, inventory, lambda _hit: None,
                    zone_reader=lambda _save: zone,
                    notify_zone=zone_alerts.append,
                )
                self.assertEqual([item["status"] for item in zone_alerts], ["correct", "incorrect"])
                self.assertEqual(zone_alerts[-1]["status"], "incorrect")

                # Uma fase diferente com a mesma classificação não repete o alerta.
                zone.update({"key": 1103, "no": 3, "label": "1-3 Normal"})
                alert.poll_once(
                    state, watch, accounts, prices, inventory, lambda _hit: None,
                    zone_reader=lambda _save: zone,
                    notify_zone=zone_alerts.append,
                )
            self.assertEqual([item["status"] for item in zone_alerts], ["correct", "incorrect"])
            self.assertIn("zone_statuses", alert._read_json(state, {}))

    def test_aviso_local_de_zona_mostra_classificacao_e_notifica_discord(self):
        alert_data = {
            "type": "zone_status", "status": "incorrect", "item": "Shadow Bow",
            "conta": "Conta 1", "zone": "1-2 Normal", "expected": "1-1 Normal",
            "reason": "Esta fase não está entre as zonas conhecidas.",
        }
        output = io.StringIO()
        with (
            mock.patch.object(alert.tbh_discord, "send_alert") as send,
            redirect_stdout(output),
        ):
            alert.notify_zone_status(alert_data)
        self.assertIn("ZONA INCORRETA — VERIFICA ZONA", output.getvalue())
        self.assertIn("1-2 Normal", output.getvalue())
        send.assert_called_once_with(alert_data)

    def test_plague_fora_da_zona_do_item_e_incorreta(self):
        status, _, _ = alert._evaluate_zone(
            {"act": 22, "no": 2, "diff": "PLAGUE", "diff_index": None, "plague": True},
            self.TORMENT_DROP,
        )
        self.assertEqual(status, "incorrect")

    def test_plague_na_mesma_fase_sem_dificuldade_pede_verificacao(self):
        plague_drop = [[22, 2, 90, 3, "", 0, 0, 0, 0, 1]]
        status, _, _ = alert._evaluate_zone(
            {"act": 22, "no": 2, "diff": "PLAGUE", "diff_index": None, "plague": True},
            plague_drop,
        )
        self.assertEqual(status, "verify")

    def test_leitor_de_save_devolve_stage_e_plague_sem_inventar_dificuldade(self):
        import tbh_inventario as inventory

        normal_save = {"commonSaveData": {"currentStageKey": 1101, "currentStageWave": 4}}
        plague_save = {"commonSaveData": {"currentStageKey": 201302}}
        stages = {1101: {"act": 1, "no": 1, "diff": "NORMAL"}}
        with (
            mock.patch.object(inventory, "_save_legivel", return_value="save"),
            mock.patch.object(inventory, "_carregar_stages", return_value=stages),
            mock.patch.object(inventory, "_es3_decrypt", return_value=normal_save),
        ):
            normal = inventory.zona_atual_da_conta("save")
        with (
            mock.patch.object(inventory, "_save_legivel", return_value="save"),
            mock.patch.object(inventory, "_carregar_stages", return_value={}),
            mock.patch.object(inventory, "_es3_decrypt", return_value=plague_save),
        ):
            plague = inventory.zona_atual_da_conta("save")

        self.assertEqual((normal["act"], normal["no"], normal["diff_index"], normal["wave"]), (1, 1, 0, 4))
        self.assertEqual(plague["label"], "22-2 Plague")
        self.assertEqual((plague["act"], plague["no"], plague["diff_index"]), (22, 2, None))
        status, _, _ = alert._evaluate_zone(plague, self.TORMENT_DROP)
        self.assertEqual(status, "incorrect")
        status_same_place, _, _ = alert._evaluate_zone(
            plague, [[22, 2, 90, 3, "", 0, 0, 0, 0, 1]],
        )
        self.assertEqual(status_same_place, "verify")


if __name__ == "__main__":
    unittest.main()
