import sys
import unittest
from pathlib import Path
import importlib

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import routers.auth as auth_router
import config as config_module
from config import settings


class AuthConfigTests(unittest.TestCase):
    def test_auth_router_prefix(self):
        self.assertEqual(auth_router.router.prefix, "/api/auth")

    def test_get_auth_config_exposes_register_flag(self):
        original = settings.ALLOW_REGISTER
        try:
            settings.ALLOW_REGISTER = True
            enabled = auth_router.get_auth_config()
            self.assertTrue(enabled.allow_register)

            settings.ALLOW_REGISTER = False
            disabled = auth_router.get_auth_config()
            self.assertFalse(disabled.allow_register)
        finally:
            settings.ALLOW_REGISTER = original

    def test_demo_seed_enabled_env_parsing(self):
        import os

        original = os.environ.get("HALF_DEMO_SEED_ENABLED")
        try:
            os.environ.pop("HALF_DEMO_SEED_ENABLED", None)
            self.assertTrue(importlib.reload(config_module).settings.DEMO_SEED_ENABLED)

            os.environ["HALF_DEMO_SEED_ENABLED"] = "false"
            self.assertFalse(importlib.reload(config_module).settings.DEMO_SEED_ENABLED)

            os.environ["HALF_DEMO_SEED_ENABLED"] = "0"
            self.assertFalse(importlib.reload(config_module).settings.DEMO_SEED_ENABLED)

            os.environ["HALF_DEMO_SEED_ENABLED"] = "true"
            self.assertTrue(importlib.reload(config_module).settings.DEMO_SEED_ENABLED)
        finally:
            if original is None:
                os.environ.pop("HALF_DEMO_SEED_ENABLED", None)
            else:
                os.environ["HALF_DEMO_SEED_ENABLED"] = original
            importlib.reload(config_module)


if __name__ == "__main__":
    unittest.main()
