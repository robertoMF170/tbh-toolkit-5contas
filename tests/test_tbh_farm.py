import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tbh_farm as farm


def sample_market():
    items = {
        "Quiet Bow (Rare) A": {"sell": 0.19, "vol": 0},
        "Quiet Bow (Legendary) A": {"sell": 0.20, "vol": 0},
        "Quiet Bow (Celestial) A": {"sell": None, "vol": 0},
        "Daily Bow (Beyond) A": {"sell": 8.0, "vol": 30},
    }
    # Fill the global rankings so the build-only 20-cent option is not daily.
    for index in range(100):
        items[f"Market item {index} (Cosmic) A"] = {
            "sell": 3.0 + index,
            "vol": 1000,
        }
    return items


class TestBuildFarm(unittest.TestCase):
    def setUp(self):
        self.market = sample_market()
        self.cache = mock.patch.object(farm, "_DAILY_CACHE", None)
        self.cache.start()
        self.prices = mock.patch.object(farm, "_load_precos", return_value=(self.market, 123))
        self.prices.start()
        self.addCleanup(self.prices.stop)
        self.addCleanup(self.cache.stop)

    def test_alternativa_de_20_centimos_fica_so_na_farm_da_build(self):
        build = {
            "sections": [{
                "hero": "Archer (level 90)",
                "gear": ["weapon:Quiet Bow", "offhand:Daily Bow"],
            }],
        }
        daily_before = farm.daily_set()
        candidates = farm.itens_diarios_para_build(build)
        candidate_names = {candidate[3] for candidate in candidates}

        self.assertIn("Quiet Bow (Legendary) A", candidate_names)
        self.assertNotIn("Quiet Bow (Rare) A", candidate_names)
        self.assertNotIn("Quiet Bow (Celestial) A", candidate_names)
        self.assertIn("Daily Bow (Beyond) A", candidate_names)
        self.assertNotIn("Quiet Bow (Legendary) A", daily_before)

        with (
            mock.patch.object(farm, "_info_for_market_name", return_value=None),
            mock.patch.object(farm, "_drop_html_for_name", return_value="drop"),
            mock.patch.object(farm, "_progresso_resumo", return_value=""),
        ):
            build_html = farm.render_farm_para_build(build)
            dashboard_html = farm.render_farm_op_section()

        self.assertIn("Quiet Bow (Legendary) A", build_html)
        self.assertIn("alternativas ≥ €0,20", build_html)
        self.assertNotIn("Quiet Bow (Legendary) A", dashboard_html)
        self.assertEqual(farm.daily_set(), daily_before)

    def test_limite_minimo_e_preco_invalido(self):
        self.assertEqual(farm._market_sell_price({"sell": "0.20"}), 0.20)
        self.assertEqual(farm._market_sell_price({"sell": "preço indisponível"}), 0.0)
        self.assertEqual(farm._market_sell_price({"sell": float("nan")}), 0.0)
        self.assertEqual(farm._market_sell_price({"sell": float("inf")}), 0.0)


if __name__ == "__main__":
    unittest.main()
