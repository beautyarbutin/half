import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import routers.settings as settings_router
from services.prompt_settings import validate_plan_co_location_guidance


class PollingSettingsValidationTests(unittest.TestCase):
    def test_settings_router_imports(self):
        self.assertEqual(settings_router.router.prefix, "/api/settings")

    def test_validate_global_polling_payload_accepts_valid_values(self):
        payload = {
            "polling_interval_min": 15,
            "polling_interval_max": 30,
            "polling_start_delay_minutes": 2,
            "polling_start_delay_seconds": 30,
            "task_timeout_minutes": 45,
        }
        coerced = settings_router._validate_global_polling_payload(payload)
        self.assertEqual(coerced, payload)

    def test_validate_global_polling_payload_rejects_invalid_range(self):
        with self.assertRaises(Exception) as ctx:
            settings_router._validate_global_polling_payload({
                "polling_interval_min": 31,
                "polling_interval_max": 30,
            })
        self.assertIn("polling_interval_min must be <= polling_interval_max", str(ctx.exception))

    def test_validate_global_polling_payload_rejects_invalid_task_timeout(self):
        for value in (0, 121):
            with self.assertRaises(Exception) as ctx:
                settings_router._validate_global_polling_payload({
                    "task_timeout_minutes": value,
                })
            self.assertIn("task_timeout_minutes must be 1-120 minutes", str(ctx.exception))

    def test_prompt_settings_validator_rejects_empty_guidance(self):
        for value in ("", "   ", None):
            with self.assertRaises(ValueError):
                validate_plan_co_location_guidance(value)

    def test_prompt_settings_validator_accepts_text_guidance(self):
        self.assertEqual(validate_plan_co_location_guidance("自定义规则"), "自定义规则")


if __name__ == "__main__":
    unittest.main()
