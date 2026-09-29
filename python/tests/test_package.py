import importlib
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]

class PackageTests(unittest.TestCase):
    def test_public_import(self):
        with patch.dict(sys.modules, {'serial': types.SimpleNamespace(Serial=None)}):
            with patch.object(sys, 'path', [str(ROOT / 'python')] + sys.path):
                package = importlib.import_module('bamboo_actuator')
                self.assertEqual(package.__all__, ['BambooActuator'])
                self.assertEqual(package.BambooActuator.__name__, 'BambooActuator')
