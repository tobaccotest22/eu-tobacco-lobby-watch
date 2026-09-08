"""
Tests du compteur d'échecs consécutifs de scripts/fetch_lobbyfacts.py.

Sans dépendance externe : lancer avec `python scripts/test_fetch_lobbyfacts_streaks.py`
(ou `python -m unittest` depuis scripts/). bs4/pypdf sont stubés car
fetch_lobbyfacts les importe au niveau module mais on ne les exerce pas ici.
"""

import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(__file__))
for _name in ("bs4", "pypdf"):
    if _name not in sys.modules:
        _mod = types.ModuleType(_name)
        _mod.BeautifulSoup = object
        _mod.PdfReader = object
        sys.modules[_name] = _mod

import fetch_lobbyfacts as F  # noqa: E402


class FailureStreakTests(unittest.TestCase):
    def test_echec_isole_ne_declenche_pas_dechec_du_job(self):
        """Une seule nuit en échec : compteur = 1, aucune panne durable signalée."""
        streaks = {}
        value = F.bump_streak(streaks, "354946837243-73", "ec_meetings", failed=True)
        self.assertEqual(value, 1)
        self.assertEqual(F.durable_failures(streaks), [])

    def test_deux_echecs_consecutifs_declenchent_lalerte(self):
        """Deux nuits consécutives en échec sur le même point / la même org :
        le compteur atteint le seuil et la clé remonte dans durable_failures
        (ce qui provoque sys.exit(1) dans main)."""
        streaks = {}
        F.bump_streak(streaks, "354946837243-73", "ec_meetings", failed=True)  # nuit 1
        # nuit 2 : on repart de l'état persisté et on ré-échoue
        value = F.bump_streak(streaks, "354946837243-73", "ec_meetings", failed=True)
        self.assertEqual(value, 2)
        self.assertGreaterEqual(F.STREAK_ALERT_THRESHOLD, 2)
        self.assertEqual(
            F.durable_failures(streaks), ["354946837243-73:ec_meetings"]
        )

    def test_un_succes_remet_le_compteur_a_zero(self):
        """Après un échec, un succès sur le même point remet le compteur à 0 :
        pas d'accumulation de faux positifs sur des accidents réseau espacés."""
        streaks = {}
        F.bump_streak(streaks, "354946837243-73", "ec_meetings", failed=True)
        self.assertEqual(streaks["354946837243-73:ec_meetings"], 1)
        value = F.bump_streak(streaks, "354946837243-73", "ec_meetings", failed=False)
        self.assertEqual(value, 0)
        self.assertEqual(F.durable_failures(streaks), [])
        # et un échec ultérieur repart bien de 1, pas de 2
        self.assertEqual(
            F.bump_streak(streaks, "354946837243-73", "ec_meetings", failed=True), 1
        )

    def test_points_suivis_independamment_par_organisation(self):
        """Une org peut être en panne durable sur ec_meetings tout en
        réussissant sur fiche_registre : les compteurs ne se mélangent pas."""
        streaks = {}
        F.bump_streak(streaks, "347372799139-19", "ec_meetings", failed=True)
        F.bump_streak(streaks, "347372799139-19", "ec_meetings", failed=True)
        F.bump_streak(streaks, "347372799139-19", "fiche_registre", failed=False)
        self.assertEqual(
            F.durable_failures(streaks), ["347372799139-19:ec_meetings"]
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
