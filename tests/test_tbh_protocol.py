import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tbh_protocol


class TestFarmLauncher(unittest.TestCase):
    def test_titulo_identifica_e_sanitiza_a_conta(self):
        self.assertEqual(tbh_protocol._titulo_farm("Conta 1"), "TBH FARM - Conta 1")
        self.assertEqual(tbh_protocol._titulo_farm('Conta "1"'), "TBH FARM - Conta _1_")
        self.assertEqual(tbh_protocol._titulo_farm("Conta 1 (geek1781)"), "TBH FARM - Conta 1 (geek1781)")
        self.assertEqual(tbh_protocol._titulo_farm(""), "TBH FARM - Todas as contas")

    def test_abre_run_farm_com_conta_no_titulo_e_ambiente(self):
        with tempfile.TemporaryDirectory() as root:
            bat = os.path.join(root, "run_farm.bat")
            with mock.patch.object(tbh_protocol, "ROOT", root), \
                 mock.patch.object(tbh_protocol.os, "name", "nt"), \
                 mock.patch.object(tbh_protocol.os.path, "isfile", return_value=True), \
                 mock.patch.object(tbh_protocol.subprocess, "Popen") as popen:
                self.assertTrue(tbh_protocol._abrir_run_farm("Conta 1"))

            args, kwargs = popen.call_args
            self.assertEqual(args[0][0:2], ["cmd.exe", "/K"])
            self.assertIn("title TBH FARM - Conta 1", args[0][2])
            self.assertIn(os.path.basename(bat), args[0][2])
            self.assertEqual(kwargs["cwd"], root)
            self.assertEqual(kwargs["creationflags"], getattr(tbh_protocol.subprocess, "CREATE_NEW_CONSOLE", 0))
            self.assertEqual(kwargs["env"]["TBH_FARM_CONTA"], "Conta 1")
            self.assertEqual(kwargs["env"]["TBH_FARM_TITULO"], "TBH FARM - Conta 1")

    def test_nao_abre_em_sistemas_sem_cmd(self):
        with mock.patch.object(tbh_protocol.os, "name", "posix"), \
             mock.patch.object(tbh_protocol.subprocess, "Popen") as popen:
            self.assertFalse(tbh_protocol._abrir_run_farm("Conta 1"))
            popen.assert_not_called()

    def test_adicionar_alvo_abre_o_bat_com_a_conta(self):
        with mock.patch.object(tbh_protocol.os.path, "exists", return_value=True), \
             mock.patch.object(tbh_protocol.subprocess, "run", return_value=mock.Mock(returncode=0)) as run, \
             mock.patch.object(tbh_protocol, "_abrir_run_farm", return_value=True) as abrir:
            tbh_protocol._handle_farm("tbh://farm?add=Shadow%20Bow&conta=Conta%201")

        args = run.call_args.args[0]
        self.assertEqual(args[args.index("--add") + 1], "Shadow Bow")
        self.assertEqual(args[args.index("--conta") + 1], "Conta 1")
        abrir.assert_called_once_with("Conta 1")
        run.assert_called_once()

    def test_adicionar_sem_conta_abre_o_bat_em_modo_todas(self):
        with mock.patch.object(tbh_protocol.os.path, "exists", return_value=True), \
             mock.patch.object(tbh_protocol.subprocess, "run", return_value=mock.Mock(returncode=0)), \
             mock.patch.object(tbh_protocol, "_abrir_run_farm", return_value=True) as abrir:
            tbh_protocol._handle_farm("tbh://farm?add=Shadow%20Bow")

        abrir.assert_called_once_with("")

    def test_nao_abre_bat_se_adicionar_alvo_falhar(self):
        with mock.patch.object(tbh_protocol.os.path, "exists", return_value=True), \
             mock.patch.object(tbh_protocol.subprocess, "run", return_value=mock.Mock(returncode=1)), \
             mock.patch.object(tbh_protocol, "_abrir_run_farm") as abrir:
            tbh_protocol._handle_farm("tbh://farm?add=Shadow%20Bow&conta=Conta%201")

        abrir.assert_not_called()


if __name__ == "__main__":
    unittest.main()
