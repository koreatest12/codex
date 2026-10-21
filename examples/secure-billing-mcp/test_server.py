"""Local-only checks; no external API requests or billable services."""
import importlib.util
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('billing_mcp_example', Path(__file__).with_name('server.py'))
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = server.SecurityAndBillingConfig()
        self.config.SAFE_BASE_DIR = Path(self.temp.name) / 'safe'
        self.config.SAFE_BASE_DIR.mkdir()
        self.guard = server.BillingAndSecurityGuard(self.config)

    def test_rate_limit_blocks_sixteenth_call(self):
        with patch.object(server.time, 'time', return_value=100):
            for _ in range(15):
                self.guard.verify_rate_limit()
            with self.assertRaises(RuntimeError):
                self.guard.verify_rate_limit()
        with patch.object(server.time, 'time', return_value=161):
            self.guard.verify_rate_limit()

    def test_budget_limit_and_invalid_costs(self):
        self.guard.verify_and_charge_budget(5)
        with self.assertRaises(RuntimeError):
            self.guard.verify_and_charge_budget(.01)
        for cost in [-1, float('nan'), float('inf')]:
            with self.assertRaises(ValueError):
                self.guard.verify_and_charge_budget(cost)
        self.assertEqual(self.guard.accumulated_cost_usd, 5)

    def test_daily_budget_reset(self):
        self.guard.verify_and_charge_budget(5)
        with patch.object(server.time, 'time', return_value=self.guard.day_start_time + 86401):
            self.guard.verify_and_charge_budget(1)
        self.assertEqual(self.guard.accumulated_cost_usd, 1)

    def test_paths_and_symlink_escape(self):
        self.assertEqual(self.guard.validate_safe_path('note.txt'), self.config.SAFE_BASE_DIR / 'note.txt')
        sibling = self.config.SAFE_BASE_DIR.with_name('safe-other')
        sibling.mkdir()
        link = self.config.SAFE_BASE_DIR / 'link'
        link.symlink_to(sibling, target_is_directory=True)
        for path in ['../outside.txt', str(sibling / 'note.txt'), 'link/note.txt']:
            with self.assertRaises(PermissionError):
                self.guard.validate_safe_path(path)

    def test_output_including_marker_stays_within_limit(self):
        for limit in [5, 3000]:
            self.config.MAX_RESPONSE_CHARS = limit
            result = self.guard.truncate_output('x' * 4000)
            self.assertLessEqual(len(result), limit)
        self.assertEqual(self.guard.truncate_output('ok'), 'ok')

    def test_rejected_input_not_logged(self):
        sensitive = 'private-test-value;'
        with self.assertLogs(server.logger, level=logging.ERROR) as captured:
            with self.assertRaises(ValueError):
                self.guard.sanitize_inputs((sensitive,), {})
        self.assertNotIn(sensitive, '\n'.join(captured.output))

    def test_file_tool_and_simulated_api(self):
        (self.config.SAFE_BASE_DIR / 'note.txt').write_text('hello', encoding='utf-8')
        with patch.object(server, 'guard', self.guard):
            self.assertEqual(server.read_workspace_file('note.txt'), 'hello')
            self.assertLessEqual(len(server.call_paid_external_api('demo')), 3000)
            self.assertIn('잔여 예산', server.get_budget_status())

    def test_budget_rejection_does_not_execute_tool(self):
        called = []
        @server.secure_and_budget_guard(estimated_cost_usd=6)
        def operation():
            called.append(True)
        with patch.object(server, 'guard', self.guard):
            result = operation()
        self.assertIn('[실행 거부됨]', result)
        self.assertEqual(called, [])

    def test_mcp_tools_registered(self):
        import asyncio
        tools = asyncio.run(server.mcp.list_tools())
        self.assertEqual({tool.name for tool in tools}, {
            'read_workspace_file', 'call_paid_external_api', 'get_budget_status',
        })


if __name__ == '__main__':
    unittest.main()
