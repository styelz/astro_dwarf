import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QGuiApplication

from astro_dwarf.device_worker import (
    _allows_ble_fallback,
    _claimed_ip_conflict,
    _connect,
)
from astro_dwarf.domain import Device
from astro_dwarf.qt_backend import AppBackend, TelescopeProcess
from astro_dwarf.storage import SessionStore


def _app() -> QGuiApplication:
    return QGuiApplication.instance() or QGuiApplication([])


class FakeTelescopeProcess(QObject):
    logReceived = Signal(str, str)
    progressReceived = Signal(str, str, float)
    statusReceived = Signal(str, str)
    telemetryReceived = Signal(dict)
    availabilityChanged = Signal()

    def __init__(self, device: Device, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.device = device
        self.connected = False
        self.configured = True
        self.busy = False
        self._reject_link = False
        self._connect_cb = None
        self.disconnect_count = 0
        self.claimed_ips: list[str] = []

    def start(self) -> None:
        return

    def shutdown(self, wait: bool = True) -> None:
        return

    def send(self, *args, **kwargs) -> int:
        return 0

    def connect_device(self, callback, claimed_ips=None) -> None:
        self._reject_link = False
        self.claimed_ips = [str(ip).strip() for ip in (claimed_ips or []) if str(ip).strip()]
        self._connect_cb = callback

    def finish_connect(self, ok: bool, result) -> None:
        TelescopeProcess._connected(self, ok, result, self._connect_cb)

    def emit_connected_event(self) -> None:
        if not self._reject_link and not self.connected:
            self.connected = True
            self.availabilityChanged.emit()

    def disconnect_device(self, callback=None) -> None:
        self._reject_link = True
        self.disconnect_count += 1
        self.connected = False
        self.availabilityChanged.emit()
        if callback:
            callback(True, None)


def _configured_device(name: str, ip_address: str) -> Device:
    return Device(
        name=name,
        ip_address=ip_address,
        latitude=-37.8,
        longitude=144.9,
        location_configured=True,
    )


class ConnectLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="astro-connect-"))
        store = SessionStore(self.tmp)
        self.real = _configured_device("DWARF #1", "10.0.0.5")
        self.dummy = _configured_device("DWARF #2", "")
        store.devices.save(self.real)
        store.devices.save(self.dummy)
        self.fakes: dict[str, FakeTelescopeProcess] = {}

        def install(backend, device, reconnect=False):
            old = backend._workers.pop(device.id, None)
            if old is not None:
                old.shutdown(wait=False)
            worker = FakeTelescopeProcess(device, backend)
            backend._workers[device.id] = worker
            self.fakes[device.id] = worker
            return worker

        self._patcher = mock.patch.object(AppBackend, "_create_worker", install)
        self._patcher.start()
        self.backend = AppBackend(self.tmp)
        self.toasts: list[tuple[str, str, str]] = []
        self.backend.toast.connect(lambda text, level, detail: self.toasts.append((text, level, detail)))

    def tearDown(self) -> None:
        self.backend.shutdown()
        self._patcher.stop()

    def _view(self, device_id: str) -> dict:
        return next(item for item in self.backend.devices if item["id"] == device_id)

    def _log_text(self) -> str:
        return " ".join(entry["message"] for entry in self.backend._log_model._all)

    def test_cancel_then_late_success_stays_offline(self) -> None:
        self.backend.connectDevice(self.real.id)
        self.assertEqual(self._view(self.real.id)["status"], "Connecting")
        self.backend.cancelConnect(self.real.id)
        self.assertEqual(self._view(self.real.id)["status"], "Cancelling")
        worker = self.fakes[self.real.id]
        worker.emit_connected_event()
        worker.finish_connect(True, {"ip_address": "10.0.0.5", "telemetry": {"battery_percent": 80}})
        view = self._view(self.real.id)
        self.assertFalse(view["connected"])
        self.assertEqual(view["status"], "Offline")
        self.assertGreaterEqual(worker.disconnect_count, 2)
        self.assertFalse(worker.connected)
        self.assertIn("Connection cancelled", self._log_text())

    def test_false_connect_result_is_readable(self) -> None:
        self.backend.connectDevice(self.real.id)
        self.fakes[self.real.id].finish_connect(True, False)
        self.assertEqual(self._view(self.real.id)["status"], "Offline")
        detail = next((item[2] for item in self.toasts if item[0] == "Connection failed"), "")
        self.assertNotIn("False", detail)
        self.assertIn("Could not reach the telescope", detail)
        self.assertIn("Could not reach the telescope", self._log_text())

    def test_dummy_does_not_claim_another_device_ip(self) -> None:
        self.backend.connectDevice(self.dummy.id)
        self.assertIn("10.0.0.5", self.fakes[self.dummy.id].claimed_ips)
        self.fakes[self.dummy.id].finish_connect(
            True,
            {"ip_address": "10.0.0.5", "telemetry": {"battery_percent": 50}},
        )
        view = self._view(self.dummy.id)
        self.assertFalse(view["connected"])
        self.assertEqual(view["status"], "Offline")
        saved = self.backend.store.devices.get(self.dummy.id)
        self.assertEqual(saved.ip_address, "")
        self.assertGreaterEqual(self.fakes[self.dummy.id].disconnect_count, 1)
        self.assertIn("already saved as DWARF #1", self._log_text())

    def test_connect_without_worker_does_not_raise(self) -> None:
        self.backend._workers.pop(self.real.id)
        self.backend.connectDevice(self.real.id)
        self.assertEqual(self._view(self.real.id)["status"], "Offline")
        self.assertIn("worker is not running", self._log_text())


class WorkerConnectPolicyTests(unittest.TestCase):
    def test_ble_fallback_only_for_empty_or_ap_ip(self) -> None:
        self.assertTrue(_allows_ble_fallback(""))
        self.assertTrue(_allows_ble_fallback("192.168.88.1"))
        self.assertFalse(_allows_ble_fallback("10.0.0.5"))

    def test_claimed_ip_conflict(self) -> None:
        with mock.patch("astro_dwarf.device_worker._device", {"_claimed_ips": ["10.0.0.5"]}):
            self.assertIn("already saved", _claimed_ip_conflict("10.0.0.5"))
            self.assertEqual(_claimed_ip_conflict("10.0.0.9"), "")

    def test_sta_ip_skips_bluetooth_fallback(self) -> None:
        with mock.patch("astro_dwarf.device_worker._device", {"ip_address": "10.0.0.5", "ble_enabled": True}), \
             mock.patch("astro_dwarf.device_worker._check_connect_cancelled"), \
             mock.patch("astro_dwarf.device_worker._handshake", return_value=None), \
             mock.patch("astro_dwarf.device_worker._safe_disconnect"), \
             mock.patch("astro_dwarf.device_worker.log"), \
             mock.patch("astro_dwarf.device_worker.provision_bluetooth") as ble:
            with self.assertRaisesRegex(RuntimeError, "Could not reach 10.0.0.5"):
                _connect()
            ble.assert_not_called()


if __name__ == "__main__":
    unittest.main()
