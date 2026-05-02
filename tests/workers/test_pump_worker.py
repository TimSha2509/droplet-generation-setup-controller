import queue
import threading
import time

from droplet_lab.devices.pump_fake import FakePump
from droplet_lab.state import ExperimentState
from droplet_lab.storage import ExperimentDirectory
from droplet_lab.workers.pump_worker import PumpWorker, SetSpeedCommand


def _run_worker(
    tmp_path, pump, state, *, duration_s=0.4, log_interval_s=0.1
) -> tuple[ExperimentDirectory, threading.Event]:
    exp = ExperimentDirectory.create(base_dir=tmp_path, experiment_id="X")
    cmd_q: queue.Queue[SetSpeedCommand] = queue.Queue()
    stop = threading.Event()
    error = threading.Event()
    worker = PumpWorker(
        pump=pump,
        state=state,
        command_queue=cmd_q,
        stop_event=stop,
        error_event=error,
        log_interval_s=log_interval_s,
        experiment_dir=exp,
    )
    t = threading.Thread(target=worker.run)
    t.start()
    try:
        time.sleep(duration_s)
        stop.set()
        t.join(timeout=2.0)
    finally:
        if t.is_alive():
            t.join(timeout=1.0)
    return exp, error


def test_writes_pump_csv_rows(tmp_path) -> None:
    state = ExperimentState()
    state.update(step_index=1, set_speed_rpm=200)
    pump = FakePump()
    with pump:
        exp, error = _run_worker(tmp_path, pump, state, duration_s=0.35, log_interval_s=0.1)
    assert not error.is_set()
    text = (exp.root / "pump.csv").read_text()
    assert "set_speed_rpm" in text
    assert text.count("\n") >= 3  # header + at least 2 rows


def test_consumes_set_speed_command(tmp_path) -> None:
    state = ExperimentState()
    state.update(step_index=1, set_speed_rpm=0)
    pump = FakePump(acceleration_rpm_per_s=10000)
    with pump:
        exp = ExperimentDirectory.create(base_dir=tmp_path, experiment_id="X")
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
    # After stop, the worker safely sets target back to 0.
    assert pump.get_target_speed_rpm() == 0


def test_sets_error_event_on_pump_failure(tmp_path) -> None:
    class BoomPump(FakePump):
        def get_actual_speed_rpm(self):
            raise RuntimeError("device disconnected")

    pump = BoomPump()
    state = ExperimentState()
    state.update(step_index=1, set_speed_rpm=0)
    with pump:
        exp, error = _run_worker(tmp_path, pump, state, duration_s=0.3)
    assert error.is_set()
