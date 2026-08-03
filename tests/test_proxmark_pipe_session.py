from __future__ import annotations

import time
import unittest
from unittest.mock import Mock
from pathlib import Path
from types import SimpleNamespace

from bambu_rfid_diag.options import TimeoutOptions
from bambu_rfid_diag.proxmark import (
    ProxmarkError,
    ProxmarkRunner,
    _marker_completed,
    _strip_marker_lines,
)


class _FakeProcess:
    def __init__(self) -> None:
        self.returncode = None
        self.stdin = SimpleNamespace()

    def poll(self):
        return self.returncode


class MarkerSessionTests(unittest.TestCase):
    def _runner(self) -> ProxmarkRunner:
        layout = SimpleNamespace(root=Path('.'), client_dir=Path('.'))
        runner = ProxmarkRunner(
            layout,
            None,
            timeouts=TimeoutOptions(
                startup_seconds=2,
                idle_seconds=2,
                command_seconds=2,
                operation_seconds=10,
            ),
        )
        runner.process = _FakeProcess()
        runner._started_at = time.monotonic()
        return runner

    def test_marker_requires_command_echo_and_rem_completion(self) -> None:
        marker = b'BRW_DONE_1234'
        self.assertFalse(_marker_completed(b'[usb|stdin] pm3 --> rem ' + marker, marker))
        complete = (
            b'[usb|stdin] pm3 --> rem ' + marker + b'\n'
            b'[+] 2026-08-02 remark: ' + marker + b' \n'
        )
        self.assertTrue(_marker_completed(complete, marker))

    def test_marker_lines_are_removed_from_command_output(self) -> None:
        marker = 'BRW_DONE_1234'
        output = (
            '[usb|stdin] pm3 --> hw version\n'
            '[+] useful output\n'
            f'[usb|stdin] pm3 --> rem {marker}\n'
            f'[+] remark: {marker}\n'
        )
        self.assertEqual(_strip_marker_lines(output, marker), '[usb|stdin] pm3 --> hw version\n[+] useful output')

    def test_startup_sends_marker_before_waiting(self) -> None:
        runner = self._runner()
        events: list[str] = []

        def write_line(line: str) -> None:
            events.append(f'write:{line.split()[0]}')
            marker = line.split()[-1]
            payload = (
                f'[usb|stdin] pm3 --> rem {marker}\n'
                f'[+] 2026-08-02 remark: {marker} \n'
            ).encode('ascii')
            for byte in payload:
                runner._output_queue.put(bytes([byte]))

        runner._write_line = write_line  # type: ignore[method-assign]
        runner._perform_startup_handshake()
        self.assertEqual(events, ['write:rem'])

    def test_execute_streams_lines_without_exposing_marker(self) -> None:
        events: list[tuple[str, object]] = []
        layout = SimpleNamespace(root=Path('.'), client_dir=Path('.'))
        runner = ProxmarkRunner(
            layout, None,
            timeouts=TimeoutOptions(2, 2, 2, 10),
            on_event=lambda event, payload: events.append((event, payload)),
        )
        runner.process = _FakeProcess()
        runner._started_at = time.monotonic()
        pending_command = ''

        def write_line(line: str) -> None:
            nonlocal pending_command
            if not line.startswith('rem '):
                pending_command = line
                return
            marker_value = line.split()[-1]
            payload = (
                f'[usb|stdin] pm3 --> {pending_command}\n'
                '[+] first line\n'
                '[+] second line\n'
                f'[usb|stdin] pm3 --> rem {marker_value}\n'
                f'[+] remark: {marker_value} \n'
            ).encode('ascii')
            for byte in payload:
                runner._output_queue.put(bytes([byte]))

        runner._write_line = write_line  # type: ignore[method-assign]
        result = runner._execute('hw version')
        names = [event for event, _ in events]
        self.assertEqual(names[0], 'command_started')
        self.assertEqual(names[-1], 'command_finished')
        output_lines = [str(payload) for event, payload in events if event == 'command_output']
        self.assertTrue(any('first line' in line for line in output_lines))
        self.assertTrue(any('second line' in line for line in output_lines))
        self.assertFalse(any('BRW_DONE_' in line for line in output_lines))
        self.assertEqual(result.returncode, 0)

    def test_execute_waits_for_following_marker_not_idle_prompt(self) -> None:
        runner = self._runner()
        pending_command = ''

        def write_line(line: str) -> None:
            nonlocal pending_command
            if not line.startswith('rem '):
                pending_command = line
                return
            marker = line.split()[-1]
            payload = (
                f'[usb|stdin] pm3 --> {pending_command}\n'
                '[+] command completed\n'
                f'[usb|stdin] pm3 --> rem {marker}\n'
                f'[+] 2026-08-02 remark: {marker} \n'
            ).encode('ascii')
            for byte in payload:
                runner._output_queue.put(bytes([byte]))

        runner._write_line = write_line  # type: ignore[method-assign]
        result = runner._execute('hw version')
        self.assertEqual(result.returncode, 0)
        self.assertFalse(result.timed_out)
        self.assertIn('command completed', result.output)
        self.assertNotIn('BRW_DONE_', result.output)

    def test_closed_runner_cannot_be_reopened(self) -> None:
        runner = self._runner()
        runner._closed = True
        with self.assertRaises(ProxmarkError):
            runner.open()

    def test_exited_runner_requires_a_new_session(self) -> None:
        runner = self._runner()
        runner.process.returncode = 1
        with self.assertRaises(ProxmarkError):
            runner.open()

    def test_close_is_idempotent_and_joins_reader(self) -> None:
        runner = self._runner()
        runner.process.returncode = 0
        reader = Mock()
        reader.is_alive.return_value = False
        runner._reader_thread = reader
        runner.close()
        runner.close()
        reader.join.assert_called_once_with(timeout=2)



if __name__ == '__main__':
    unittest.main()
