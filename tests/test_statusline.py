import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unicodedata
import unittest

from helpers import ROOT

WINDOW = 'CLAUDE_CODE_AUTO_COMPACT_WINDOW'


class StatusLine(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.script = self.home / 'statusline-zh.py'
        self.settings = self.home / 'settings.json'
        shutil.copyfile(ROOT / 'scripts/vps/claude-statusline-zh.py', self.script)
        self.data = {
            'model': {'display_name': '示例模型'},
            'effort': {'level': 'high'},
            'context_window': {
                'context_window_size': 200000,
                'current_usage': {'input_tokens': 3000, 'cache_creation_input_tokens': 0,
                                  'cache_read_input_tokens': 180000},
            },
        }

    def run_status(self, columns='80', **environment):
        env = dict(os.environ, COLUMNS=columns)
        env.pop(WINDOW, None)
        env.update(environment)
        result = subprocess.run([sys.executable, '-I', str(self.script)], input=json.dumps(self.data),
                                env=env, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        return re.sub(r'\x1b\[[0-9;]*m', '', result.stdout), result.stderr

    def test_wide_and_narrow_windows_keep_all_fields_and_bars(self):
        now = int(time.time())
        self.settings.write_text(json.dumps({'env': {WINDOW: '272000'}}))
        self.data.update({
            'prompt_cache': {'warm': True, 'hit_ratio': 0.94, 'expires_at': now + 65},
            'rate_limits': {'five_hour': {'used_percentage': 25, 'resets_at': now + 900},
                            'seven_day': {'used_percentage': 42, 'resets_at': now + 86400}},
            'cost': {'total_cost_usd': 0.25},
        })
        for columns in (80, 56):
            with self.subTest(columns=columns):
                display, errors = self.run_status(str(columns))
                self.assertEqual(errors, '')
                for label in ('示例模型', 'high', '183k/272k窗', '输出', '缓存', '5小时', '本周', '重置', '$0.25'):
                    self.assertIn(label, display)
                self.assertRegex(display, r'余\d+:\d{2}')
                self.assertEqual(len(re.findall(r'\[[█░]+\]', display)), 3)
                for line in display.splitlines():
                    cells = sum(2 if unicodedata.east_asian_width(char) in ('W', 'F') else 1 for char in line)
                    self.assertLessEqual(cells, columns - 4, line)

    def test_missing_or_invalid_settings_leave_the_model_window_visible(self):
        for settings in (None, '{"env":{"' + WINDOW + '":""}}', '{'):
            with self.subTest(settings=settings):
                if settings is not None:
                    self.settings.write_text(settings)
                display, _ = self.run_status('unknown')
                self.assertIn('183k/200k', display)
                self.assertIn('本周', display)

    def test_effective_compact_window_takes_priority_over_settings(self):
        self.settings.write_text(json.dumps({'env': {WINDOW: '272000'}}))
        display, errors = self.run_status(**{WINDOW: '300000'})
        self.assertEqual(errors, '')
        self.assertIn('183k/300k窗', display)

    def test_output_speed_uses_the_last_response_block_and_reuses_its_cache(self):
        transcript = self.home / 'example.jsonl'
        request = {'type': 'api-request', 'id': 'req-example', 'timestamp': '2026-01-01T00:00:00.000Z'}
        response = {'type': 'assistant', 'requestRef': 'req-example',
                    'timestamp': '2026-01-01T00:00:06.000Z', 'message': {'usage': {'output_tokens': 4}}}
        last_block = dict(response, timestamp='2026-01-01T00:00:10.000Z')
        transcript.write_text(''.join(json.dumps(record) + '\n' for record in (request, response, last_block)))
        self.data['transcript_path'] = str(transcript)
        display, errors = self.run_status()
        self.assertEqual(errors, '')
        self.assertRegex(display, r'输出\s*≈0\.4\s*t/s')
        (cache,) = (self.home / 'cache/statusline-zh').glob('*.json')
        self.assertEqual(stat.S_IMODE(cache.stat().st_mode), 0o600)
        modified = cache.stat().st_mtime_ns
        self.assertIn('≈0.4', self.run_status()[0])
        self.assertEqual(cache.stat().st_mtime_ns, modified)

        with transcript.open('a') as stream:
            stream.write('[]\n')
        display, errors = self.run_status()
        self.assertIn('输出 日志异常', display)
        self.assertIn('示例模型', display)
        self.assertIn('本周', display)
        self.assertIn('transcript record is not a JSON object', errors)


if __name__ == '__main__':
    unittest.main()
