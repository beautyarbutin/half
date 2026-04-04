import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import routers.agents as agents_router


class AgentResetTimeTests(unittest.TestCase):
    def test_normalize_beijing_datetime_from_aware_utc(self):
        value = datetime.fromisoformat("2026-04-04T12:24:00+00:00")
        normalized = agents_router._normalize_beijing_datetime(value)
        self.assertEqual(normalized, datetime(2026, 4, 4, 20, 24))

    def test_advance_reset_time_uses_beijing_wall_clock(self):
        current = datetime(2026, 4, 4, 20, 24)
        mocked_now = datetime(2026, 4, 4, 20, 32, tzinfo=agents_router.BEIJING_TZ)
        with patch.object(agents_router, "datetime") as mock_datetime:
            mock_datetime.now.return_value = mocked_now
            next_value = agents_router._advance_reset_time(current, 5, hours=True)
        self.assertEqual(next_value, datetime(2026, 4, 5, 1, 24))

    def test_normalize_reset_marks_confirmation_when_auto_advanced(self):
        agent = type("AgentStub", (), {
            "short_term_reset_at": datetime(2026, 4, 4, 20, 24),
            "short_term_reset_interval_hours": 5,
            "short_term_reset_needs_confirmation": False,
            "long_term_reset_at": None,
            "long_term_reset_interval_days": None,
            "long_term_reset_needs_confirmation": False,
            "updated_at": None,
        })()
        mocked_now = datetime(2026, 4, 4, 20, 32, tzinfo=agents_router.BEIJING_TZ)
        with patch.object(agents_router, "datetime") as mock_datetime:
            mock_datetime.now.return_value = mocked_now
            changed = agents_router._normalize_agent_reset_times(agent, mark_confirmation=True)
        self.assertTrue(changed)
        self.assertTrue(agent.short_term_reset_needs_confirmation)
        self.assertEqual(agent.short_term_reset_at, datetime(2026, 4, 5, 1, 24))

    def test_manual_update_clears_confirmation_flags(self):
        agent = type("AgentStub", (), {
            "short_term_reset_needs_confirmation": True,
            "long_term_reset_needs_confirmation": True,
        })()
        agents_router._clear_confirmation_flags_on_manual_update(
            agent,
            {"short_term_reset_at": datetime(2026, 4, 5, 1, 24), "long_term_reset_interval_days": 7},
        )
        self.assertFalse(agent.short_term_reset_needs_confirmation)
        self.assertFalse(agent.long_term_reset_needs_confirmation)


if __name__ == "__main__":
    unittest.main()
