import queue
import threading
import time
from pathlib import Path

from droplet_lab.devices.pump_fake import FakePump
from droplet_lab.state import ExperimentState
from droplet_lab.storage import ExperimentDirectory, combo_folder_name
from droplet_lab.workers.pump_worker import PumpWorker, SetSpeedCommand


def _make_combo_folder(
    exp: ExperimentDirectory, idx: int, rpm: int, freq: float, amp: float
) -> Path:
    folder = exp.steps_dir / combo_folder_name(idx, rpm, freq, amp)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "images").mkdir(exist_ok=True)
    return folder


def test_writes_pump_csv_into_combo_folder(tmp_path: Path) -> None:
    state = ExperimentState()
    state.update(combo_index=1, set_speed_rpm=200, set_frequency_hz=20.0, set_amplitude_vpp=3.0)
    exp = ExperimentDirectory.create(base_dir=tmp_path, experiment_id="X")
    _make_combo_folder(exp, 1, 200, 20.0, 3.0)

    cmd_q: queue.Queue[SetSpeedCommand] = queue.Queue()
    stop = threading.Event()
    error = threading.Event()
    pump = FakePump()
    with pump:
        worker = PumpWorker(
            pump=pump,
            state=state,
            command_queue=cmd_q,
            stop_event=stop,
            error_event=error,
            log_interval_s=0.05,
            experiment_dir=exp,
        )
        t = threading.Thread(target=worker.run)
        t.start()
        time.sleep(0.3)
        stop.set()
        t.join(timeout=2.0)
    assert not error.is_set()
    combo_folder = exp.steps_dir / combo_folder_name(1, 200, 20.0, 3.0)
    text = (combo_folder / "pump.csv").read_text()
    assert "set_frequency_hz" in text.splitlines()[0]
    assert text.count("\n") >= 2


def test_rotates_csv_when_combo_changes(tmp_path: Path) -> None:
    state = ExperimentState()
    state.update(combo_index=1, set_speed_rpm=200, set_frequency_hz=20.0, set_amplitude_vpp=3.0)
    exp = ExperimentDirectory.create(base_dir=tmp_path, experiment_id="X")
    _make_combo_folder(exp, 1, 200, 20.0, 3.0)
    _make_combo_folder(exp, 2, 200, 20.0, 5.0)

    cmd_q: queue.Queue[SetSpeedCommand] = queue.Queue()
    stop = threading.Event()
    error = threading.Event()
    pump = FakePump()
    with pump:
        worker = PumpWorker(
            pump=pump,
            state=state,
            command_queue=cmd_q,
            stop_event=stop,
            error_event=error,
            log_interval_s=0.04,
            experiment_dir=exp,
        )
        t = threading.Thread(target=worker.run)
        t.start()
        time.sleep(0.2)
        state.update(combo_index=2, set_speed_rpm=200, set_frequency_hz=20.0, set_amplitude_vpp=5.0)
        time.sleep(0.2)
        stop.set()
        t.join(timeout=2.0)
    assert not error.is_set()
    combo_a = exp.steps_dir / combo_folder_name(1, 200, 20.0, 3.0) / "pump.csv"
    combo_b = exp.steps_dir / combo_folder_name(2, 200, 20.0, 5.0) / "pump.csv"
    assert combo_a.exists()
    assert combo_b.exists()
    assert combo_a.read_text().splitlines()[0].startswith("timestamp_utc;")
    assert combo_b.read_text().splitlines()[0].startswith("timestamp_utc;")


def test_consumes_set_speed_command(tmp_path: Path) -> None:
    state = ExperimentState()
    state.update(combo_index=1, set_speed_rpm=0, set_frequency_hz=20.0, set_amplitude_vpp=3.0)
    pump = FakePump(acceleration_rpm_per_s=10000)
    with pump:
        exp = ExperimentDirectory.create(base_dir=tmp_path, experiment_id="X")
        _make_combo_folder(exp, 1, 0, 20.0, 3.0)
        cmd_q: queue.Queue[SetSpeedCommand] = queue.Queue()
        stop = threading.Event()
        error = threading.Event()
        worker = PumpWorker(
            pump=pump,
            state=state,
            command_queue=cmd_q,
            stop_event=stop,
            error_event=error,
            log_interval_s=0.05,
            experiment_dir=exp,
        )
        t = threading.Thread(target=worker.run)
        t.start()
        cmd_q.put(SetSpeedCommand(rpm=350))
        time.sleep(0.3)
        target_before_stop = pump.get_target_speed_rpm()
        stop.set()
        t.join(timeout=2.0)
    assert target_before_stop == 350
    assert pump.get_target_speed_rpm() == 0


def test_sets_error_event_on_pump_failure(tmp_path: Path) -> None:
    class BoomPump(FakePump):
        def get_actual_speed_rpm(self):
            raise RuntimeError("device disconnected")

    pump = BoomPump()
    state = ExperimentState()
    state.update(combo_index=1, set_speed_rpm=0, set_frequency_hz=20.0, set_amplitude_vpp=3.0)
    with pump:
        exp = ExperimentDirectory.create(base_dir=tmp_path, experiment_id="X")
        _make_combo_folder(exp, 1, 0, 20.0, 3.0)
        cmd_q: queue.Queue[SetSpeedCommand] = queue.Queue()
        stop = threading.Event()
        error = threading.Event()
        worker = PumpWorker(
            pump=pump,
            state=state,
            command_queue=cmd_q,
            stop_event=stop,
            error_event=error,
            log_interval_s=0.05,
            experiment_dir=exp,
        )
        t = threading.Thread(target=worker.run)
        t.start()
        time.sleep(0.3)
        stop.set()
        t.join(timeout=2.0)
    assert error.is_set()
