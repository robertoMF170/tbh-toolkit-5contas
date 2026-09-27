# -*- coding: utf-8 -*-
r"""test_tbh_visitas.py - testes para o servidor de estatisticas tbh_visitas.

Cobertura:
  - carregar/guardar (roundtrip, JSON corrompido, raiz nao-dict)
  - registar (sessoes, eventos, github_click, associacoes cruzadas)
  - _associa (limite de 50 entradas)
  - _escrever_stats (totais, online, ordenacao, por_device sem id vazio)
  - servidor HTTP real (CORS/OPTIONS, APIs de visitas e farm, ficheiros/erros)

Correr:  python -m unittest -v test_tbh_visitas
"""

import http.client
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tbh_visitas as sv


AGORA = 1_000_000.0


def dados_vazios() -> dict:
    return {"ips": {}, "devices": {}}


class TestCarregarGuardar(unittest.TestCase):
    def test_carregar_inexistente_devolve_vazio(self):
        with tempfile.TemporaryDirectory() as tmp:
            dados = sv.carregar(os.path.join(tmp, "nao_existe.json"))
        self.assertEqual(dados, {"ips": {}, "devices": {}})

    def test_roundtrip_guardar_carregar(self):
        dados = {
            "ips": {"1.2.3.4": {"visitas": 2, "last": 5.0, "github": 1}},
            "devices": {"abc": {"visitas": 1, "last": 5.0}},
        }
        with tempfile.TemporaryDirectory() as tmp:
            caminho = os.path.join(tmp, "var", "visitas.json")
            sv.guardar(caminho, dados)
            self.assertTrue(os.path.isfile(caminho))
            self.assertEqual(sv.carregar(caminho), dados)

    def test_carregar_json_corrompido(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = os.path.join(tmp, "visitas.json")
            with open(caminho, "w", encoding="utf-8") as fh:
                fh.write("{isto nao e json valido")
            self.assertEqual(sv.carregar(caminho), {"ips": {}, "devices": {}})

    def test_carregar_raiz_nao_dict(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = os.path.join(tmp, "visitas.json")
            with open(caminho, "w", encoding="utf-8") as fh:
                json.dump([1, 2, 3], fh)
            self.assertEqual(sv.carregar(caminho), {"ips": {}, "devices": {}})


class TestRegistar(unittest.TestCase):
    def test_primeiro_ping_conta_visita(self):
        dados = dados_vazios()
        self.assertTrue(sv.registar(dados, "1.1.1.1", "dev-a", "ping", agora=AGORA))
        self.assertEqual(dados["ips"]["1.1.1.1"]["visitas"], 1)
        self.assertEqual(dados["devices"]["dev-a"]["visitas"], 1)
        self.assertEqual(dados["ips"]["1.1.1.1"]["last"], AGORA)
        self.assertEqual(dados["ips"]["1.1.1.1"]["first"], AGORA)

    def test_mesma_sessao_nao_conta_duas_visitas(self):
        dados = dados_vazios()
        sv.registar(dados, "1.1.1.1", "dev-a", "ping", agora=AGORA)
        self.assertTrue(sv.registar(dados, "1.1.1.1", "dev-a", "ping", agora=AGORA + 60))
        self.assertEqual(dados["ips"]["1.1.1.1"]["visitas"], 1)
        self.assertEqual(dados["ips"]["1.1.1.1"]["last"], AGORA + 60)

    def test_heartbeat_antigo_nao_muda_nada(self):
        dados = dados_vazios()
        sv.registar(dados, "1.1.1.1", "dev-a", "ping", agora=AGORA)
        self.assertFalse(sv.registar(dados, "1.1.1.1", "dev-a", "ping", agora=AGORA - 10))
        self.assertEqual(dados["ips"]["1.1.1.1"]["visitas"], 1)
        self.assertEqual(dados["ips"]["1.1.1.1"]["last"], AGORA)

    def test_gap_maior_que_sessao_conta_nova_visita(self):
        dados = dados_vazios()
        sv.registar(dados, "1.1.1.1", "dev-a", "ping", agora=AGORA)
        sv.registar(dados, "1.1.1.1", "dev-a", "ping", agora=AGORA + sv.SESSAO_SEGUNDOS + 1)
        self.assertEqual(dados["ips"]["1.1.1.1"]["visitas"], 2)

    def test_evento_visit_nao_duplo_na_mesma_sessao(self):
        dados = dados_vazios()
        sv.registar(dados, "1.1.1.1", "dev-a", "visit", agora=AGORA)
        sv.registar(dados, "1.1.1.1", "dev-a", "visit", agora=AGORA + 1)
        self.assertEqual(dados["ips"]["1.1.1.1"]["visitas"], 1)

    def test_evento_invalido_e_none_viram_ping(self):
        dados = dados_vazios()
        sv.registar(dados, "1.1.1.1", "dev-a", "bananas", agora=AGORA)
        sv.registar(dados, "2.2.2.2", "dev-b", None, agora=AGORA)
        self.assertEqual(dados["ips"]["1.1.1.1"]["visitas"], 1)
        self.assertEqual(dados["ips"]["2.2.2.2"]["visitas"], 1)

    def test_github_click_incrementa_dois_registos(self):
        dados = dados_vazios()
        sv.registar(dados, "1.1.1.1", "dev-a", "github_click", agora=AGORA)
        sv.registar(dados, "1.1.1.1", "dev-a", "GITHUB_CLICK", agora=AGORA + 1)
        self.assertEqual(dados["ips"]["1.1.1.1"]["visitas"], 1)
        self.assertEqual(dados["ips"]["1.1.1.1"]["github"], 2)
        self.assertEqual(dados["devices"]["dev-a"]["github"], 2)

    def test_associacoes_cruzadas(self):
        dados = dados_vazios()
        sv.registar(dados, "1.1.1.1", "dev-a", "ping", agora=AGORA)
        self.assertEqual(dados["ips"]["1.1.1.1"]["devices"], ["dev-a"])
        self.assertEqual(dados["devices"]["dev-a"]["ips"], ["1.1.1.1"])

    def test_device_vazio_cria_registo_sem_associar(self):
        dados = dados_vazios()
        sv.registar(dados, "1.1.1.1", "", "ping", agora=AGORA)
        self.assertIn("", dados["devices"])
        self.assertEqual(dados["ips"]["1.1.1.1"]["devices"], [])


class TestAssocia(unittest.TestCase):
    def _rec(self):
        return sv._registo(dados_vazios(), "ips", "1.1.1.1", AGORA)

    def test_ignora_valor_vazio(self):
        rec = self._rec()
        sv._associa(rec, "devices", "", limite=5)
        self.assertEqual(rec["devices"], [])

    def test_limite_50_descarta_mais_antigos(self):
        dados = dados_vazios()
        sv._registo(dados, "ips", "1.1.1.1", AGORA)
        rec = dados["ips"]["1.1.1.1"]
        for i in range(52):
            sv._associa(rec, "devices", "dev-%02d" % i)
        self.assertEqual(len(rec["devices"]), 50)
        self.assertNotIn("dev-00", rec["devices"])
        self.assertNotIn("dev-01", rec["devices"])
        self.assertEqual(rec["devices"][-1], "dev-51")


class TestEscreverStats(unittest.TestCase):
    def test_totais_online_e_ordenacao(self):
        dados = dados_vazios()
        agora = __import__("time").time()
        dados["ips"]["10.0.0.1"] = {"visitas": 3, "github": 2, "last": agora - 5, "devices": ["b", "a"]}
        dados["ips"]["10.0.0.2"] = {"visitas": 1, "github": 1, "last": agora - 9999, "devices": []}
        dados["devices"]["dev-x"] = {"visitas": 4, "github": 2, "last": agora - 10, "ips": ["10.0.0.1"]}
        dados["devices"][""] = {"visitas": 99, "github": 99, "last": agora - 1, "ips": []}
        stats = sv._escrever_stats(dados)
        self.assertEqual(stats["total_visitas"], 4)
        self.assertEqual(stats["total_github"], 3)
        self.assertEqual(stats["ips_online"], 1)
        self.assertEqual(stats["online_agora"], 1)
        self.assertGreaterEqual(stats["agora"], agora)
        self.assertEqual([e["id"] for e in stats["por_ip"]], ["10.0.0.1", "10.0.0.2"])
        self.assertEqual([e["id"] for e in stats["por_device"]], ["dev-x"])
        self.assertEqual(stats["por_ip"][0]["visitas"], 3)
        self.assertEqual(stats["por_ip"][0]["devices"], ["a", "b"])
        self.assertTrue(stats["por_ip"][0]["online"])
        self.assertFalse(stats["por_ip"][1]["online"])
        self.assertTrue(stats["por_device"][0]["online"])

    def test_vazio(self):
        stats = sv._escrever_stats(dados_vazios())
        self.assertEqual(stats["total_visitas"], 0)
        self.assertEqual(stats["total_github"], 0)
        self.assertEqual(stats["por_ip"], [])
        self.assertEqual(stats["por_device"], [])
        self.assertEqual(stats["online_agora"], 0)


class TestServidorHTTP(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.root = self._dir.name
        with open(os.path.join(self.root, "minhas_builds.html"), "w", encoding="utf-8") as fh:
            fh.write("window.__TBH_FARM_API_TOKEN__='__TBH_FARM_API_TOKEN_VALUE__';")
        with open(os.path.join(self.root, "segredo.txt"), "w", encoding="utf-8") as fh:
            fh.write("secreto")
        self.db = os.path.join(self.root, "var", "visitas.json")
        self._db_antigo = sv._DB_PATH[0]
        self._active_antigo = sv._ACTIVE_SERVER[0]
        self.server = sv.arrancar(0, self.root, self.db)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.porta = self.server.server_address[1]
        self.base = "http://127.0.0.1:%d" % self.porta

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        sv._DB_PATH[0] = self._db_antigo
        sv._ACTIVE_SERVER[0] = self._active_antigo
        self._dir.cleanup()

    def _pedido(self, caminho, dados=None, metodo=None, headers=None):
        corpo = json.dumps(dados).encode("utf-8") if dados is not None else None
        request_headers = dict(headers or {})
        if corpo is not None:
            request_headers.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(self.base + caminho, data=corpo,
                                     method=metodo or ("POST" if corpo else "GET"), headers=request_headers)
        return urllib.request.urlopen(req, timeout=10)

    def _pedido_erro(self, caminho, dados=None, metodo=None, headers=None):
        try:
            resp = self._pedido(caminho, dados, metodo, headers)
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, exc.read()
            finally:
                exc.close()
        self.fail("esperava HTTPError, obteve %s" % resp.status)

    def _farm_headers(self, origin=None, token=None):
        headers = {
            "X-TBH-Farm-Token": token if token is not None else self.server.tbh_farm_token,
        }
        if origin is not None:
            headers["Origin"] = origin
        return headers

    def test_options_cors(self):
        req = urllib.request.Request(self.base + "/api/visitas", method="OPTIONS")
        with urllib.request.urlopen(req, timeout=10) as resp:
            self.assertEqual(resp.status, 204)
            self.assertEqual(resp.headers["Access-Control-Allow-Origin"], "*")
            self.assertIn("POST", resp.headers["Access-Control-Allow-Methods"])
            self.assertEqual(int(resp.headers["Content-Length"]), 0)

    def test_post_visit(self):
        with self._pedido("/api/visitas", {"device": "teste", "event": "visit"}) as resp:
            self.assertEqual(resp.status, 200)
            corpo = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(corpo["ok"])
        self.assertEqual(corpo["stats"]["total_visitas"], 1)
        self.assertEqual(sv.carregar(self.db)["devices"]["teste"]["visitas"], 1)

    def test_post_ping_e_get_stats(self):
        with self._pedido("/api/visitas", {"device": "dev1", "event": "ping"}) as resp:
            self.assertEqual(resp.status, 200)
            json.loads(resp.read().decode("utf-8"))
        with self._pedido("/api/visitas") as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers["Content-Type"], "application/json; charset=utf-8")
            stats = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(stats["total_visitas"], 1)
        self.assertEqual(stats["total_github"], 0)
        self.assertIn("por_ip", stats)
        self.assertIn("por_device", stats)

    def test_post_github_click(self):
        with self._pedido("/api/visitas", {"device": "dev1", "event": "github_click"}) as resp:
            corpo = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(corpo["ok"])
        self.assertEqual(corpo["stats"]["total_github"], 1)
        self.assertEqual(sv.carregar(self.db)["devices"]["dev1"]["github"], 1)

    def test_dashboard_injeta_token_por_resposta_e_nao_guarda_segredo(self):
        with self._pedido("/") as resp:
            html = resp.read().decode("utf-8")
        self.assertEqual(html, "window.__TBH_FARM_API_TOKEN__='" + self.server.tbh_farm_token + "';")
        with open(os.path.join(self.root, "minhas_builds.html"), encoding="utf-8") as fh:
            disk_html = fh.read()
        self.assertEqual(disk_html, "window.__TBH_FARM_API_TOKEN__='__TBH_FARM_API_TOKEN_VALUE__';")
        self.assertNotIn(self.server.tbh_farm_token, disk_html)

    def test_api_farm_get_expoe_estado_pausado(self):
        with (
            mock.patch("tbh_farm_alert.load_targets", return_value=[
                {"name": "Item", "conta": "Conta 1", "paused": True},
            ]),
            mock.patch("tbh_farm_alert._watch_data", return_value={"targets": [], "hits": []}),
        ):
            with self._pedido("/api/farm", metodo="GET", headers=self._farm_headers(origin=self.base)) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(data["targets"], [{"name": "Item", "conta": "Conta 1", "paused": True}])

    def test_executar_acao_farm_pausa_e_retomada_sem_remover_historico(self):
        history = [{"name": "Item", "conta": "Conta 1", "qtd": 1, "acknowledged": True}]
        with (
            mock.patch("tbh_farm_alert.set_target_paused", return_value=True) as pause_target,
            mock.patch("tbh_farm_alert._watch_data", return_value={"targets": [], "hits": history}),
            mock.patch("tbh_farm_alert.load_targets", return_value=[
                {"name": "Item", "conta": "Conta 1", "paused": True},
            ]),
        ):
            paused = sv.executar_acao_farm({"action": "pause", "name": "Item", "conta": "Conta 1"})
        self.assertTrue(paused["changed"])
        self.assertEqual(paused["targets"], [{"name": "Item", "conta": "Conta 1", "paused": True}])
        self.assertEqual(paused["hits"], history)
        pause_target.assert_called_once_with("Item", "Conta 1", paused=True)

        with (
            mock.patch("tbh_farm_alert.set_target_paused", return_value=True) as resume_target,
            mock.patch("tbh_farm_alert._watch_data", return_value={"targets": [], "hits": history}),
            mock.patch("tbh_farm_alert.load_targets", return_value=[
                {"name": "Item", "conta": "Conta 1"},
            ]),
        ):
            resumed = sv.executar_acao_farm({"action": "resume", "name": "Item", "conta": "Conta 1"})
        self.assertTrue(resumed["changed"])
        self.assertEqual(resumed["targets"], [{"name": "Item", "conta": "Conta 1", "paused": False}])
        self.assertEqual(resumed["hits"], history)
        resume_target.assert_called_once_with("Item", "Conta 1", paused=False)

    def test_api_farm_get_exige_origem_local_e_token(self):
        code, body = self._pedido_erro("/api/farm", metodo="GET")
        self.assertEqual(code, 403)
        self.assertIn("nao autorizado", json.loads(body.decode("utf-8"))["erro"])
        code, _ = self._pedido_erro("/api/farm", metodo="GET", headers=self._farm_headers(origin="http://evil.example"))
        self.assertEqual(code, 403)
        with (
            mock.patch("tbh_farm_alert.load_targets", return_value=[]),
            mock.patch("tbh_farm_alert._watch_data", return_value={"targets": [], "hits": []}),
        ):
            with self._pedido("/api/farm", metodo="GET", headers=self._farm_headers(origin=self.base)) as resp:
                self.assertEqual(json.loads(resp.read().decode("utf-8"))["targets"], [])

    def test_api_farm_post_pausa_usa_a_acao_separada(self):
        with mock.patch.object(sv, "executar_acao_farm", return_value={
            "ok": True, "changed": True, "action": "pause", "message": "Alerta pausado: Item",
            "targets": [{"name": "Item", "conta": "geek1781", "paused": True}], "hits": [],
        }) as action:
            with self._pedido("/api/farm", {"action": "pause", "name": "Item", "conta": "geek1781"},
                              headers=self._farm_headers(origin=self.base)) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(data["ok"])
        self.assertTrue(data["targets"][0]["paused"])
        action.assert_called_once_with({"action": "pause", "name": "Item", "conta": "geek1781"})

    def test_api_farm_post_regista_item_sem_protocolo_do_browser(self):
        with mock.patch.object(sv, "executar_acao_farm", return_value={
            "ok": True, "changed": True, "action": "add", "message": "Alerta registado: Item",
            "targets": [{"name": "Item", "conta": "geek1781"}], "hits": [],
        }) as action:
            with self._pedido("/api/farm", {"action": "add", "name": "Item", "conta": "geek1781"},
                              headers=self._farm_headers(origin=self.base)) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(data["ok"])
        self.assertEqual(data["targets"], [{"name": "Item", "conta": "geek1781"}])
        action.assert_called_once_with({"action": "add", "name": "Item", "conta": "geek1781"})

    def test_adicionar_build_pela_api_local_valida_link_e_regenera(self):
        url = "https://tbhindex.com/pt/builds/321"
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "config", "builds.json")
            os.makedirs(os.path.dirname(state_file))
            with open(state_file, "w", encoding="utf-8") as fh:
                json.dump({"urls": ["https://tbhindex.com/pt/builds/252"]}, fh)
            with (
                mock.patch("tbh_site.STATE_FILE", state_file),
                mock.patch("tbh_site.resolve_url", return_value=url) as resolve,
                mock.patch("tbh_site.save_urls") as save,
                mock.patch.object(sv, "gerar_builds", return_value=True) as generate,
            ):
                result = sv.executar_acao_farm({"action": "add-build", "name": url})
        self.assertTrue(result["ok"])
        self.assertTrue(result["changed"])
        resolve.assert_called_once_with(url)
        save.assert_called_once_with([
            "https://tbhindex.com/pt/builds/252", url,
        ])
        generate.assert_called_once()

    def test_adicionar_build_rejeita_outro_dominio_sem_resolver(self):
        with mock.patch("tbh_site.resolve_url") as resolve:
            with self.assertRaisesRegex(ValueError, "tbhindex.com"):
                sv.executar_acao_farm({"action": "add-build", "name": "https://tbhindex.com.evil.example/pt/builds/321"})
        resolve.assert_not_called()


    def test_api_farm_post_recusa_token_origem_conteudo_e_request_invalido(self):
        code, _ = self._pedido_erro("/api/farm", {"action": "add", "name": "Item"},
                                    headers={"Origin": self.base, "X-TBH-Farm-Token": "errado"})
        self.assertEqual(code, 403)
        code, _ = self._pedido_erro("/api/farm", {"action": "add", "name": "Item"},
                                    headers={"Origin": "http://evil.example", "X-TBH-Farm-Token": self.server.tbh_farm_token})
        self.assertEqual(code, 403)
        code, _ = self._pedido_erro("/api/farm", {"action": "add", "name": "Item"},
                                    headers={**self._farm_headers(origin=self.base), "Content-Type": "text/plain"})
        self.assertEqual(code, 415)
        with mock.patch.object(sv, "executar_acao_farm", side_effect=ValueError("Pedido invalido")):
            code, _ = self._pedido_erro("/api/farm", {"action": "add", "name": ""},
                                        headers=self._farm_headers(origin=self.base))
        self.assertEqual(code, 400)

    def test_dashboard_nao_publica_ficheiros_privados(self):
        for caminho in ("/segredo.txt", "/.env", "/var/farm_watch.json", "/config/baus.json"):
            code, body = self._pedido_erro(caminho)
            self.assertIn(code, (403, 404))
            self.assertNotIn(b"secreto", body)

    def test_traversal_bloqueado(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.porta, timeout=10)
        conn.request("GET", "/../segredo.txt")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 403)
        self.assertIn(b"caminho invalido", resp.read())
        conn.close()

    def test_ficheiro_inexistente(self):
        codigo, corpo = self._pedido_erro("/nao_existe.txt")
        self.assertEqual(codigo, 404)
        self.assertIn(b"privado ou nao publicado", corpo)

    def test_post_rota_desconhecida(self):
        codigo, corpo = self._pedido_erro("/api/outra", {"x": 1})
        self.assertEqual(codigo, 404)
        self.assertIn("rota desconhecida", json.loads(corpo.decode("utf-8"))["erro"])

    def test_post_device_muito_longo(self):
        nome = "x" * 100
        with self._pedido("/api/visitas", {"device": nome}) as resp:
            self.assertTrue(json.loads(resp.read().decode("utf-8"))["ok"])
        dados = sv.carregar(self.db)
        self.assertIn("x" * 64, dados["devices"])
        self.assertNotIn(nome, dados["devices"])
        self.assertTrue(all(len(key) <= 64 for key in dados["devices"]))

    def test_post_json_invalido(self):
        req = urllib.request.Request(self.base + "/api/visitas", data=b"{!!}", method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            corpo = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(corpo["ok"])
        self.assertEqual([key for key in sv.carregar(self.db)["devices"] if key], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
