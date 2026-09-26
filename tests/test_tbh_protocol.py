import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tbh_farm_alert
import tbh_protocol


class TestFarmProtocol(unittest.TestCase):
    def test_adicionar_so_regista_alerta_com_conta(self):
        with mock.patch.object(tbh_farm_alert, "add_target", return_value=True) as add, \
             mock.patch.object(tbh_protocol.subprocess, "Popen") as popen:
            tbh_protocol._handle_farm("tbh://farm?add=Shadow%20Bow&conta=Conta%201")

        add.assert_called_once_with("Shadow Bow", "Conta 1")
        popen.assert_not_called()

    def test_adicionar_sem_conta_regista_para_todas(self):
        with mock.patch.object(tbh_farm_alert, "add_target", return_value=True) as add:
            tbh_protocol._handle_farm("tbh://farm?add=Shadow%20Bow")

        add.assert_called_once_with("Shadow Bow", "")

    def test_nao_abre_vigia_nem_se_adicionar_item_repetido(self):
        with mock.patch.object(tbh_farm_alert, "add_target", return_value=False), \
             mock.patch.object(tbh_protocol.subprocess, "Popen") as popen:
            tbh_protocol._handle_farm("tbh://farm?add=Shadow%20Bow")

        popen.assert_not_called()

    def test_remover_alvo_com_conta(self):
        with mock.patch.object(tbh_farm_alert, "remove_target", return_value=True) as remove:
            tbh_protocol._handle_farm("tbh://farm?rm=Shadow%20Bow&conta=Conta%201")

        remove.assert_called_once_with("Shadow Bow", "Conta 1")

    def test_ack_confirma_todos_alertas_pendentes(self):
        with mock.patch.object(tbh_farm_alert, "acknowledge_hits", return_value=2) as ack:
            tbh_protocol._handle_farm("tbh://farm?ack=Shadow%20Bow")

        ack.assert_called_once_with("Shadow Bow", all_hits=False)

    def test_nao_instala_alertas_se_item_vazio(self):
        with mock.patch.object(tbh_farm_alert, "add_target") as add:
            tbh_protocol._handle_farm("tbh://farm?add=")

        add.assert_not_called()


if __name__ == "__main__":
    unittest.main()
