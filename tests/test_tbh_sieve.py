r"""
Testes do cliente SIEVE (tbh_sieve.py). Sem rede: as respostas HTTP são
"gravadas" no limite do transporte (FakeTransport). A lógica testada é a real.

Correr:  python -m unittest -v test_tbh_sieve
"""

import json
import os
import tempfile
import unittest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import tbh_sieve as sv


class FakeTransport:
    """Fila de respostas gravadas. Regista cada chamada.
    Cada item: ("ok", status, headers, body) | ("net", mensagem)."""

    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas = []

    def __call__(self, method, url, headers, data, timeout):
        self.chamadas.append({"method": method, "url": url,
                              "headers": dict(headers or {}), "data": data,
                              "timeout": timeout})
        if not self.respostas:
            raise AssertionError("transporte sem resposta gravada para " + method + " " + url)
        r = self.respostas.pop(0)
        if r[0] == "net":
            raise sv.SieveNetworkError(r[1])
        _, status, hdrs, body = r
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        return status, hdrs or {}, body


def _client(transport, **kw):
    kw.setdefault("api_key", "dc_sk_test")
    kw.setdefault("sleep", lambda *_: None)
    return sv.SieveClient(transport=transport, **kw)


class TestSegredos(unittest.TestCase):
    def test_load_from_env(self):
        old = os.environ.get(sv.API_KEY_ENV)
        os.environ[sv.API_KEY_ENV] = "dc_sk_from_env"
        try:
            self.assertEqual(sv.load_api_key(), "dc_sk_from_env")
        finally:
            if old is None:
                os.environ.pop(sv.API_KEY_ENV, None)
            else:
                os.environ[sv.API_KEY_ENV] = old

    def test_load_from_env_file(self):
        old_env = os.environ.pop(sv.API_KEY_ENV, None)
        old_file = sv.ENV_FILE
        with tempfile.TemporaryDirectory() as d:
            sv.ENV_FILE = os.path.join(d, ".env")
            with open(sv.ENV_FILE, "w", encoding="utf-8") as f:
                f.write("# comentário\nSIEVE_API_KEY=dc_sk_file\n")
            try:
                self.assertEqual(sv.load_api_key(), "dc_sk_file")
            finally:
                sv.ENV_FILE = old_file
                if old_env is not None:
                    os.environ[sv.API_KEY_ENV] = old_env

    def test_save_preserves_other_lines_and_hides_key(self):
        old_file = sv.ENV_FILE
        with tempfile.TemporaryDirectory() as d:
            sv.ENV_FILE = os.path.join(d, ".env")
            with open(sv.ENV_FILE, "w", encoding="utf-8") as f:
                f.write("OUTRA=1\n")
            try:
                sv.save_api_key("dc_sk_secreto")
                with open(sv.ENV_FILE, encoding="utf-8") as fh:
                    txt = fh.read()
                self.assertIn("OUTRA=1", txt)
                self.assertIn("SIEVE_API_KEY=dc_sk_secreto", txt)
                self.assertEqual(sv.load_api_key(), "dc_sk_secreto")
            finally:
                sv.ENV_FILE = old_file

    def test_unconfigured_raises_and_repr_hides_key(self):
        c = sv.SieveClient(api_key="", transport=FakeTransport([]))
        self.assertFalse(c.configured())
        self.assertNotIn("dc_sk", repr(c))
        with self.assertRaises(sv.SieveNotConfigured):
            c.get_scrape("x")
        c2 = sv.SieveClient(api_key="dc_sk_abc", transport=FakeTransport([]))
        self.assertNotIn("dc_sk_abc", repr(c2))
        self.assertEqual(sv.redact("erro com dc_sk_abc dentro", "dc_sk_abc"),
                         "erro com dc_sk_*** dentro")


class TestPedidos(unittest.TestCase):
    def test_start_scrape_builds_request(self):
        t = FakeTransport([("ok", 202, {}, {"status": "queued", "session_id": "s1",
                                            "poll": "/api/scrapes/s1"})])
        c = _client(t)
        r = c.start_scrape("Extrai as citações", target_urls=["https://quotes.toscrape.com"],
                           fields=["texto", "autor"])
        self.assertEqual(r["session_id"], "s1")
        ch = t.chamadas[0]
        self.assertEqual(ch["method"], "POST")
        self.assertEqual(ch["url"], sv.BASE_URL + "/api/scrapes")
        self.assertEqual(ch["headers"]["Authorization"], "Bearer dc_sk_test")
        self.assertEqual(ch["headers"]["Content-Type"], "application/json")
        corpo = json.loads(ch["data"].decode())
        self.assertEqual(corpo["instruction"], "Extrai as citações")
        self.assertEqual(corpo["target_urls"], ["https://quotes.toscrape.com"])
        self.assertEqual(corpo["compliance_mode"], "regular")

    def test_modo_invalido_e_schema_grande(self):
        c = _client(FakeTransport([]))
        with self.assertRaises(sv.SieveError):
            c.start_scrape("x", compliance_mode="banana")
        with self.assertRaises(sv.SieveError):
            c.start_scrape("x", table_shape="triangular")
        grande = {"type": "object", "x": "y" * (33 * 1024)}
        with self.assertRaises(sv.SieveError):
            c.start_scrape("x", output_schema=grande)

    def test_multipart_para_ficheiro(self):
        t = FakeTransport([("ok", 202, {}, {"status": "queued", "session_id": "d1"})])
        c = _client(t)
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("conteudo")
            caminho = f.name
        try:
            c.start_scrape("Lê o documento", file_path=caminho)
        finally:
            os.unlink(caminho)
        ch = t.chamadas[0]
        self.assertTrue(ch["headers"]["Content-Type"].startswith("multipart/form-data"))
        self.assertIn(b'name="file"; filename=', ch["data"])
        self.assertIn(b'name="instruction"', ch["data"])

    def test_file_url_relativo_recebe_base(self):
        c = _client(FakeTransport([]))
        self.assertEqual(c.file_url({"url": "/api/files/a.csv"}),
                         sv.BASE_URL + "/api/files/a.csv")
        self.assertEqual(c.file_url({"url": "https://cdn/x.csv"}), "https://cdn/x.csv")

    def test_download_file_usa_bearer(self):
        t = FakeTransport([("ok", 200, {}, b"a,b\n1,2\n")])
        c = _client(t)
        with tempfile.TemporaryDirectory() as d:
            p = c.download_file({"name": "out.csv", "url": "/api/files/out.csv"}, d)
            self.assertTrue(p.endswith("out.csv"))
            with open(p, "rb") as fh:
                self.assertEqual(fh.read(), b"a,b\n1,2\n")
        self.assertEqual(t.chamadas[0]["headers"]["Authorization"], "Bearer dc_sk_test")


class TestEstados(unittest.TestCase):
    def test_poll_running_depois_done(self):
        t = FakeTransport([
            ("ok", 200, {}, {"status": "running"}),
            ("ok", 200, {}, {"status": "running"}),
            ("ok", 200, {}, {"status": "done", "summary": "ok", "files": []}),
        ])
        c = _client(t)
        run = c.poll_scrape("s1")
        self.assertEqual(run["status"], "done")
        self.assertEqual(len(t.chamadas), 3)

    def test_poll_refused(self):
        t = FakeTransport([("ok", 200, {}, {"status": "refused",
                                            "refusal": {"code": "quota"}})])
        c = _client(t)
        with self.assertRaises(sv.SieveRefused) as ctx:
            c.poll_scrape("s1")
        self.assertEqual(ctx.exception.code, "quota")
        self.assertIn("créditos", str(ctx.exception))

    def test_poll_status_desconhecido_e_erro(self):
        t = FakeTransport([("ok", 200, {}, {"status": "banana"})])
        c = _client(t)
        with self.assertRaises(sv.SieveUnknownStatus):
            c.poll_scrape("s1")

    def test_poll_backoff_5_para_30(self):
        vistos = []
        t = FakeTransport([("ok", 200, {}, {"status": "running"})] * 8 +
                          [("ok", 200, {}, {"status": "done"})])
        c = _client(t, sleep=lambda s: vistos.append(s))
        c.poll_scrape("s1")
        self.assertEqual(vistos[0], 5.0)
        self.assertLessEqual(max(vistos), 30.0)
        self.assertGreaterEqual(len(vistos), 5)


class TestTurnos(unittest.TestCase):
    def test_followup_espera_turnos_avancarem(self):
        t = FakeTransport([
            ("ok", 200, {}, {"status": "done", "turns": 1}),   # antes: registar turnos
            ("ok", 200, {}, {"status": "done"}),               # POST /messages
            ("ok", 200, {}, {"status": "done", "turns": 1}),   # done mas ainda não avançou
            ("ok", 200, {}, {"status": "done", "turns": 2}),   # avançou -> devolve
        ])
        c = _client(t)
        run = c.send_message("s1", "Agora só os autores")
        self.assertEqual(run["turns"], 2)
        self.assertEqual(t.chamadas[1]["url"], sv.BASE_URL + "/api/scrapes/s1/messages")
        self.assertEqual(t.chamadas[1]["method"], "POST")

    def test_followup_409_espera_e_reenvia(self):
        t = FakeTransport([
            ("ok", 200, {}, {"status": "done", "turns": 1}),
            ("ok", 409, {}, {"error": "turno em curso"}),
            ("ok", 200, {}, {"status": "running", "turns": 1}),
            ("ok", 200, {}, {"status": "done", "turns": 2}),
        ])
        c = _client(t)
        run = c.send_message("s1", "repetir")
        self.assertEqual(run["turns"], 2)
        posts = [ch for ch in t.chamadas if ch["method"] == "POST"]
        self.assertEqual(len(posts), 2)  # 1.º levou 409, reenviado


class TestErros(unittest.TestCase):
    def _erro(self, status, body=None):
        t = FakeTransport([("ok", status, {}, body or {"error": "x"})])
        c = _client(t, max_retries=0)
        with self.assertRaises(sv.SieveHTTPError) as ctx:
            c.request("GET", "/api/me/credits")
        return ctx.exception

    def test_mapa_400(self):
        e = self._erro(400)
        self.assertFalse(e.retryable)
        self.assertIn("corrige", str(e))

    def test_mapa_401(self):
        e = self._erro(401, {"error": "invalid_api_key"})
        self.assertEqual(e.status, 401)
        self.assertFalse(e.retryable)

    def test_mapa_402(self):
        e = self._erro(402, {"error": "no_credits"})
        self.assertIn("créditos", str(e))

    def test_mapa_404(self):
        e = self._erro(404)
        self.assertEqual(e.status, 404)

    def test_mapa_429_retryable(self):
        e = self._erro(429)
        self.assertTrue(e.retryable)

    def test_mapa_5xx_retryable(self):
        e = self._erro(503)
        self.assertTrue(e.retryable)

    def test_429_respeita_retry_after(self):
        vistos = []
        t = FakeTransport([
            ("ok", 429, {"Retry-After": "7"}, {"error": "slow"}),
            ("ok", 200, {}, {"ok": True}),
        ])
        c = _client(t, sleep=lambda s: vistos.append(s))
        c.request("GET", "/api/me/credits")
        self.assertEqual(vistos[0], 7.0)

    def test_get_repete_5xx_com_backoff(self):
        t = FakeTransport([
            ("ok", 500, {}, {"error": "boom"}),
            ("ok", 200, {}, {"ok": True}),
        ])
        c = _client(t)
        self.assertTrue(c.request("GET", "/api/me/credits")["ok"])
        self.assertEqual(len(t.chamadas), 2)

    def test_get_repete_erro_de_rede(self):
        t = FakeTransport([
            ("net", "timeout"),
            ("ok", 200, {}, {"ok": True}),
        ])
        c = _client(t)
        self.assertTrue(c.request("GET", "/api/me/credits")["ok"])
        self.assertEqual(len(t.chamadas), 2)


class TestNaoRepetirPOST(unittest.TestCase):
    def test_post_timeout_nao_e_repetido(self):
        t = FakeTransport([("net", "timed out")])
        c = _client(t)
        with self.assertRaises(sv.SieveNetworkError):
            c.request("POST", "/api/scrapes", {"instruction": "x"}, retry_network=False)
        self.assertEqual(len(t.chamadas), 1)  # NUNCA repetiu

    def test_start_scrape_timeout_nao_duplica(self):
        t = FakeTransport([("net", "timed out")])
        c = _client(t)
        with self.assertRaises(sv.SieveNetworkError):
            c.start_scrape("Extrai isto")
        self.assertEqual(len(t.chamadas), 1)

    def test_post_5xx_pode_ser_repetido_pois_nao_criou_run(self):
        t = FakeTransport([
            ("ok", 500, {}, {"error": "boom"}),
            ("ok", 202, {}, {"status": "queued", "session_id": "s9"}),
        ])
        c = _client(t)
        r = c.start_scrape("Extrai isto")
        self.assertEqual(r["session_id"], "s9")
        self.assertEqual(len(t.chamadas), 2)


class TestPersistencia(unittest.TestCase):
    def test_session_id_gravado_antes_de_poll(self):
        with tempfile.TemporaryDirectory() as d:
            store = sv.RunStore(path=os.path.join(d, "runs.json"))
            t = FakeTransport([("ok", 202, {}, {"status": "queued", "session_id": "abc"})])
            c = _client(t, store=store)
            c.start_scrape("instrução")
            rec = store.get("abc")
            self.assertIsNotNone(rec)          # já está em disco sem ter feito poll
            self.assertEqual(rec["status"], "queued")
            self.assertEqual(rec["instruction"], "instrução")

    def test_retoma_apos_crash_sem_duplicar(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "runs.json")
            store1 = sv.RunStore(path=path)
            t1 = FakeTransport([("ok", 202, {}, {"status": "queued", "session_id": "abc"})])
            _client(t1, store=store1).start_scrape("instrução")
            # "crash": novo objeto a ler o mesmo ficheiro
            store2 = sv.RunStore(path=path)
            pendentes = store2.unfinished()
            self.assertEqual([r["session_id"] for r in pendentes], ["abc"])
            # retomar é só poll no mesmo session_id (sem novo POST /api/scrapes)
            t2 = FakeTransport([("ok", 200, {}, {"status": "done", "turns": 1})])
            run = _client(t2, store=store2).poll_scrape("abc")
            self.assertEqual(run["status"], "done")
            self.assertEqual([ch["method"] for ch in t2.chamadas], ["GET"])
            self.assertNotIn("abc", [r["session_id"] for r in sv.RunStore(path=path).unfinished()])


class TestConformidade(unittest.TestCase):
    def test_classificacao(self):
        self.assertEqual(sv.schema_status({"schema_conformance": {"status": "pass"}}), "pass")
        self.assertEqual(sv.schema_status({"schema_conformance": {"status": "partial"}}), "partial")
        self.assertEqual(sv.schema_status({"schema_conformance": {"status": "fail"}}), "fail")
        self.assertEqual(sv.schema_status({}), "no_artifact")

    def test_fail_nunca_e_limpo(self):
        run = {"schema_conformance": {"status": "fail"}}
        self.assertFalse(sv.is_clean(run))
        self.assertIn("FALHOU", sv.schema_warning(run))

    def test_partial_tem_aviso_mas_nao_e_limpo(self):
        run = {"schema_conformance": {"status": "partial"}}
        self.assertFalse(sv.is_clean(run))
        self.assertIn("parcial", sv.schema_warning(run))

    def test_pass_e_limpo(self):
        run = {"schema_conformance": {"status": "pass"}}
        self.assertTrue(sv.is_clean(run))
        self.assertEqual(sv.schema_warning(run), "")


class TestDeviceLogin(unittest.TestCase):
    def test_fluxo_pendente_slow_down_sucesso(self):
        t = FakeTransport([
            ("ok", 200, {}, {"device_code": "dev1", "user_code": "WDJB-MJHT",
                             "verification_uri": "https://s/device",
                             "verification_uri_complete": "https://s/device?code=WDJB-MJHT",
                             "expires_in": 600, "interval": 5}),
            ("ok", 400, {}, {"error": "authorization_pending"}),
            ("ok", 400, {}, {"error": "slow_down"}),
            ("ok", 200, {}, {"api_key": "dc_sk_nova", "token_type": "Bearer", "key_name": "me"}),
        ])
        vistos, mostra = [], []
        chave = sv.device_login("meu-tool", transport=t, sleep=lambda s: vistos.append(s),
                                show=mostra.append, store_key=False)
        self.assertEqual(chave, "dc_sk_nova")
        self.assertIn("WDJB-MJHT", "".join(mostra))
        self.assertNotIn("dc_sk_nova", "".join(mostra))   # a chave nunca é impressa
        self.assertEqual(vistos[0], 5.0)
        self.assertEqual(vistos[-1], 10.0)                # slow_down -> +5s

    def test_estado_do_login_guarda_e_retoma(self):
        old = sv.LOGIN_FILE
        with tempfile.TemporaryDirectory() as d:
            sv.LOGIN_FILE = os.path.join(d, "login.json")
            try:
                cod = {"device_code": "dev1", "user_code": "AB-CD",
                       "verification_uri_complete": "https://s/x",
                       "interval": 5, "expires_in": 600}
                sv.login_state_save(cod)
                st = sv.login_state_load()
                self.assertEqual(st["device_code"], "dev1")
                self.assertEqual(st["user_code"], "AB-CD")
            finally:
                sv.LOGIN_FILE = old

    def test_device_login_poll_guarda_chave_sem_imprimir(self):
        t = FakeTransport([
            ("ok", 400, {}, {"error": "authorization_pending"}),
            ("ok", 200, {}, {"api_key": "dc_sk_x"}),
        ])
        vistos, mostra = [], []
        chave = sv.device_login_poll("dev1", transport=t, sleep=lambda s: vistos.append(s),
                                     show=mostra.append, store_key=False, now=lambda: 0.0)
        self.assertEqual(chave, "dc_sk_x")
        self.assertEqual(vistos, [5.0])
        self.assertNotIn("dc_sk_x", "".join(mostra))

    def test_acesso_negado(self):
        t = FakeTransport([
            ("ok", 200, {}, {"device_code": "dev1", "expires_in": 600, "interval": 5}),
            ("ok", 400, {}, {"error": "access_denied"}),
        ])
        with self.assertRaises(sv.SieveError) as ctx:
            sv.device_login(transport=t, sleep=lambda *_: None, show=lambda *_: None,
                            store_key=False)
        self.assertIn("recusou", str(ctx.exception))

    def test_codigo_expirado(self):
        t = FakeTransport([
            ("ok", 200, {}, {"device_code": "dev1", "expires_in": 600, "interval": 5}),
            ("ok", 400, {}, {"error": "authorization_pending"}),
        ])
        rel = iter([0, 0, 10_000])
        with self.assertRaises(sv.SieveError) as ctx:
            sv.device_login(transport=t, sleep=lambda *_: None, show=lambda *_: None,
                            store_key=False, now=lambda: next(rel))
        self.assertIn("expirado", str(ctx.exception))


class TestWebhooks(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.store = sv.WebhookStore(path=os.path.join(self._dir.name, "wh.json"))

    def tearDown(self):
        self._dir.cleanup()

    def payload(self, **extra):
        d = {"event": "monitor.changed", "monitor_id": "m1", "run_id": "r1",
             "data": {"results_url": "/api/monitors/m1/runs/r1/results"}}
        d.update(extra)
        return d

    def test_segredo_errado_recusado(self):
        r = sv.handle_webhook(self.payload(), path_secret="errado",
                              expected_secret="segredo", store=self.store)
        self.assertEqual(r["http"], 404)
        self.assertFalse(self.store.seen("m1", "r1"))

    def test_segredo_correto_aceite_e_deduplicado(self):
        r1 = sv.handle_webhook(self.payload(), path_secret="segredo",
                               expected_secret="segredo", store=self.store)
        self.assertEqual(r1["http"], 200)
        self.assertFalse(r1.get("duplicado"))
        r2 = sv.handle_webhook(self.payload(), path_secret="segredo",
                               expected_secret="segredo", store=self.store)
        self.assertEqual(r2["http"], 200)
        self.assertTrue(r2["duplicado"])

    def test_fetch_results_url_quando_truncado(self):
        chamadas = []
        def fetch(monitor_id, run_id, url):
            chamadas.append((monitor_id, run_id, url))
            return {"linhas": []}
        sv.handle_webhook(self.payload(data={"truncated": True,
                                             "results_url": "/api/monitors/m1/runs/r1/results"}),
                          path_secret="segredo", expected_secret="segredo",
                          store=self.store, fetch_results=fetch)
        self.assertEqual(chamadas, [("m1", "r1", "/api/monitors/m1/runs/r1/results")])

    def test_sem_results_url_nao_faz_fetch(self):
        chamadas = []
        sv.handle_webhook(self.payload(data={"truncated": False}),
                          path_secret="segredo", expected_secret="segredo",
                          store=self.store, fetch_results=lambda *a: chamadas.append(a))
        self.assertEqual(chamadas, [])

    def test_reconciliacao_lista_runs(self):
        t = FakeTransport([("ok", 200, {}, {"runs": [{"run_id": "r1", "status": "changed"}]})])
        c = _client(t)
        r = c.monitor_runs("m1")
        self.assertEqual(r["runs"][0]["status"], "changed")
        self.assertEqual(t.chamadas[0]["url"], sv.BASE_URL + "/api/monitors/m1/runs")


if __name__ == "__main__":
    unittest.main(verbosity=2)
