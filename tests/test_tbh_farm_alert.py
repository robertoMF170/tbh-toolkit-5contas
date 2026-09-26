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


class TestAlertData(unittest.TestCase):
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
            "targets": [{"name": "Shadow Bow", "conta": "geek1781"}],
            "target_count": 1,
            "account_count": 1,
            "status": "active",
            "updated_at": "agora",
            "interval_seconds": 2,
            "unreadable_accounts": [],
        }
        output = io.StringIO()
        with mock.patch.object(alert, "watcher_status", return_value=heartbeat), redirect_stdout(output):
            result = alert.main(["--status", "--conta", "geek1781"])
        self.assertEqual(result, 0)
        self.assertIn("VIGIA ATIVO", output.getvalue())
        self.assertIn("geek1781 -> Conta 1 (geek1781)", output.getvalue())

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
                self.assertEqual(alert.poll_once(state, watch, accounts, prices, FakeInventory(), notified.append), [])
                self.assertEqual(notified, [])
                key = alert._target_key({"name": "Shadow Bow", "conta": "geek1781"})
                self.assertEqual(alert._read_json(state, {})["target_baselines"][key]["accounts"]["conta 1 (geek1781)"], 4)
                write_json(accounts, {"contas": [{"nome": "Conta 1 (geek1781)", "save": json.dumps({"Shadow Bow": 5})}]})
                hits = alert.poll_once(state, watch, accounts, prices, FakeInventory(), notified.append)
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
                ), [])
                write_json(accounts, {"contas": [{
                    "nome": "Conta 1 (geek1781)", "save": json.dumps({"Shadow Bow": 5})
                }]})
                hits = alert.poll_once(state, watch, accounts, prices, inventory, lambda hit: None)
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
                self.assertEqual(alert.poll_once(state, watch, accounts, prices, FakeInventory(), lambda hit: self.fail("false alarm")), [])
                self.assertEqual(alert.poll_once(state, watch, accounts, prices, FakeInventory(), lambda hit: self.fail("false alarm")), [])

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
                alert.poll_once(state, watch, accounts, prices, FakeInventory(), lambda hit: self.fail("false alarm"))
                write_json(accounts, {"contas": [{"nome": "Conta 1", "save": json.dumps({"Shadow Bow": 1})}]})
                notified = []
                hits = alert.poll_once(state, watch, accounts, prices, FakeInventory(), notified.append)
                self.assertEqual(hits, [{"name": "Shadow Bow", "conta": "Conta 1", "qtd": 1}])
                self.assertEqual(notified, hits)
                self.assertEqual(alert.poll_once(state, watch, accounts, prices, FakeInventory(), lambda hit: self.fail("duplicate alarm")), [])
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
                alert.poll_once(state, watch, accounts, prices, FakeInventory(), lambda hit: self.fail("false alarm"))
                write_json(accounts, {"contas": [
                    {"nome": "Conta 1", "save": json.dumps({"Shadow Bow": 0})},
                    {"nome": "Conta 2", "save": json.dumps({"Shadow Bow": 9})},
                ]})
                hits = alert.poll_once(state, watch, accounts, prices, FakeInventory(), lambda hit: None)
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
                alert.poll_once(state, watch, accounts, prices, FakeInventory(), lambda hit: self.fail("false alarm"))
                write_json(accounts, {"contas": [{"nome": "Conta 1", "save": "broken"}]})
                self.assertEqual(alert.poll_once(state, watch, accounts, prices, FakeInventory(), lambda hit: self.fail("false alarm")), [])
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
                alert.poll_once(state, watch, accounts, prices, FakeInventory(), lambda hit: self.fail("false alarm"))
                write_json(accounts, {"contas": [
                    {"nome": "Conta 1", "save": json.dumps({"Shadow Bow": 1})},
                    {"nome": "Conta 2", "save": json.dumps({"Shadow Bow": 5})},
                ]})
                self.assertEqual(alert.poll_once(state, watch, accounts, prices, FakeInventory(), lambda hit: self.fail("new account false alarm")), [])
                write_json(accounts, {"contas": [
                    {"nome": "Conta 1", "save": json.dumps({"Shadow Bow": 1})},
                    {"nome": "Conta 2", "save": json.dumps({"Shadow Bow": 6})},
                ]})
                hits = alert.poll_once(state, watch, accounts, prices, FakeInventory(), lambda hit: None)
            self.assertEqual(hits, [{"name": "Shadow Bow", "conta": "Conta 2", "qtd": 1}])

    def test_find_new_drops_respeita_a_conta_do_alvo(self):
        previous = {"Conta 1": {"Shadow Bow": 1}, "Conta 2": {"Shadow Bow": 1}}
        current = {"Conta 1": {"Shadow Bow": 1}, "Conta 2": {"Shadow Bow": 2}}
        targets = [{"name": "Shadow Bow", "conta": "Conta 1"}]
        self.assertEqual(alert.find_new_drops(previous, current, targets), [])


if __name__ == "__main__":
    unittest.main()
