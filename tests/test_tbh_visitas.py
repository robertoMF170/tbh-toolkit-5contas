# -*- coding: utf-8 -*-
r"""test_tbh_visitas.py - testes para o servidor de estatisticas tbh_visitas.

Cobertura:
  - carregar/guardar (roundtrip, JSON corrompido, raiz nao-dict)
  - registar (sessoes, eventos, github_click, associacoes cruzadas)
  - _associa (limite de 50 entradas)
  - _escrever_stats (totais, online, ordenacao, por_device sem id vazio)
  - servidor HTTP real (CORS/OPTIONS, POST/GET da API, ficheiros, erros)

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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tbh_visitas as sv


AGORA = 1_000_000.0  # timestamp fixo para testes deterministas


def dados_vazios() -> dict:
    return {"ips": {}, "devices": {}}


class TestCarregarGuardar(unittest.TestCase):
    """Persistencia: roundtrip e tolerancia a ficheiros invalidos."""

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
            lido = sv.carregar(caminho)
        self.assertEqual(lido, dados)

    def test_carregar_json_corrompido(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = os.path.join(tmp, "visitas.json")
            with open(caminho, "w", encoding="utf-8") as fh:
                fh.write("{isto nao e json valido")
            dados = sv.carregar(caminho)
        self.assertEqual(dados, {"ips": {}, "devices": {}})

    def test_carregar_raiz_nao_dict(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = os.path.join(tmp, "visitas.json")
            with open(caminho, "w", encoding="utf-8") as fh:
                json.dump([1, 2, 3], fh)
            dados = sv.carregar(caminho)
        self.assertEqual(dados, {"ips": {}, "devices": {}})


class TestRegistar(unittest.TestCase):
    """Logica de sessoes e eventos dentro de registar()."""

    def test_primeiro_ping_conta_visita(self):
        dados = dados_vazios()
        mudou = sv.registar(dados, "1.1.1.1", "dev-a", "ping", agora=AGORA)
        self.assertTrue(mudou)
        self.assertEqual(dados["ips"]["1.1.1.1"]["visitas"], 1)
        self.assertEqual(dados["devices"]["dev-a"]["visitas"], 1)
        self.assertEqual(dados["ips"]["1.1.1.1"]["last"], AGORA)
        self.assertEqual(dados["ips"]["1.1.1.1"]["first"], AGORA)

    def test_mesma_sessao_nao_conta_duas_visitas(self):
        dados = dados_vazios()
        sv.registar(dados, "1.1.1.1", "dev-a", "ping", agora=AGORA)
        mudou = sv.registar(dados, "1.1.1.1", "dev-a", "ping",
                            agora=AGORA + 60)
        # heartbeat dentro da sessao: so actualiza last
        self.assertTrue(mudou)
        self.assertEqual(dados["ips"]["1.1.1.1"]["visitas"], 1)
        self.assertEqual(dados["ips"]["1.1.1.1"]["last"], AGORA + 60)

    def test_heartbeat_antigo_nao_muda_nada(self):
        dados = dados_vazios()
        sv.registar(dados, "1.1.1.1", "dev-a", "ping", agora=AGORA)
        mudou = sv.registar(dados, "1.1.1.1", "dev-a", "ping",
                            agora=AGORA - 10)
        self.assertFalse(mudou)
        self.assertEqual(dados["ips"]["1.1.1.1"]["visitas"], 1)
        self.assertEqual(dados["ips"]["1.1.1.1"]["last"], AGORA)

    def test_gap_maior_que_sessao_conta_nova_visita(self):
        dados = dados_vazios()
        sv.registar(dados, "1.1.1.1", "dev-a", "ping", agora=AGORA)
        sv.registar(dados, "1.1.1.1", "dev-a", "ping",
                    agora=AGORA + sv.SESSAO_SEGUNDOS + 1)
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
        sv.registar(dados, "1.1.1.1", "dev-a", "GITHUB_CLICK",
                    agora=AGORA + 1)
        # nova sessao no 1.º clique conta a visita; 2.º e' so contador
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
    """_associa: ignora vazio e limita a lista a 50 entradas."""

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

import time
import http.client


class TestEscreverStats(unittest.TestCase):
    def test_totais_online_e_ordenacao(self):
        dados = dados_vazios()
        agora = time.time()
        dados["ips"]["10.0.0.1"] = {
            "visitas": 3, "github": 2, "last": agora - 5,
            "devices": ["b", "a"],
        }
        dados["ips"]["10.0.0.2"] = {
            "visitas": 1, "github": 1, "last": agora - 9999,
            "devices": [],
        }
        dados["devices"]["dev-x"] = {
            "visitas": 4, "github": 2, "last": agora - 10,
            "ips": ["10.0.0.1"],
        }
        dados["devices"][""] = {
            "visitas": 99, "github": 99, "last": agora - 1,
            "ips": [],
        }
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
        with open(os.path.join(self.root, "minhas_builds.html"), "w", encoding="utf-8") as f:
            f.write("<html><body>ola builds</body></html>")
        with open(os.path.join(self.root, "segredo.txt"), "w", encoding="utf-8") as f:
            f.write("secreto")
        self.db = os.path.join(self.root, "var", "visitas.json")
        self._db_antigo = sv._DB_PATH[0]
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
        self._dir.cleanup()

    def _pedido(self, caminho, dados=None, metodo=None):
        corpo = json.dumps(dados).encode("utf-8") if dados is not None else None
        req = urllib.request.Request(
            self.base + caminho, data=corpo,
            method=metodo or ("POST" if corpo else "GET"),
        )
        return urllib.request.urlopen(req, timeout=10)

    def _pedido_erro(self, caminho, dados=None, metodo=None):
        try:
            resp = self._pedido(caminho, dados, metodo)
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, exc.read()
            finally:
                exc.close()
        self.fail("esperava HTTPError, obteve %s" % resp.status)

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
        dados = sv.carregar(self.db)
        self.assertEqual(dados["devices"]["teste"]["visitas"], 1)

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
        # total_github soma apenas o grupo por_ip (1 ip => 1 clique),
        # mas o registo do device tambem fica com +1.
        self.assertEqual(corpo["stats"]["total_github"], 1)
        dados = sv.carregar(self.db)
        self.assertEqual(dados["devices"]["dev1"]["github"], 1)

    def test_index(self):
        for caminho in ("/", "/index.html", "/minhas_builds.html"):
            with self._pedido(caminho) as resp:
                self.assertEqual(resp.status, 200)
                self.assertIn("text/html", resp.headers["Content-Type"])
                conteudo = resp.read()
            self.assertIn(b"ola builds", conteudo)

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
        self.assertIn(b"nao encontrado", corpo)

    def test_post_rota_desconhecida(self):
        codigo, corpo = self._pedido_erro("/api/outra", {"x": 1})
        self.assertEqual(codigo, 404)
        self.assertIn("rota desconhecida", json.loads(corpo.decode("utf-8"))["erro"])

    def test_post_device_muito_longo(self):
        nome = "x" * 100
        with self._pedido("/api/visitas", {"device": nome}) as resp:
            corpo = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(corpo["ok"])
        dados = sv.carregar(self.db)
        self.assertIn("x" * 64, dados["devices"])
        self.assertNotIn(nome, dados["devices"])
        for chave in dados["devices"]:
            self.assertLessEqual(len(chave), 64)

    def test_post_json_invalido(self):
        req = urllib.request.Request(self.base + "/api/visitas", data=b"{!!}", method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            corpo = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(corpo["ok"])
        dados = sv.carregar(self.db)
        self.assertEqual([k for k in dados["devices"] if k], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
