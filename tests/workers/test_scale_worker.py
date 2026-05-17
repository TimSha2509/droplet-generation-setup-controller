import threading
import time
from pathlib import Path

from droplet_lab.devices.scale_fake import FakeScale
from droplet_lab.state import ExperimentState
from droplet_lab.storage import ExperimentDirectory
from droplet_lab.workers.scale_worker import ScaleWorker


def test_scale_worker_writes_sweep_rows_with_full_combo_tags(tmp_path: Path) -> None:
    state = ExperimentState()
    state.update(combo_index=1, set_speed_rpm=200, set_frequency_hz=20.0, set_amplitude_vpp=3.0)
    exp = ExperimentDirectory.create(base_dir=tmp_path, experiment_id="X")
    scale = FakeScale()
    stop = threading.Event()
    error = threading.Event()
    with scale:
        worker = ScaleWorker(
            scale=scale,
            state=state,
            stop_event=stop,
            error_event=error,
            log_interval_s=0.05,
            experiment_dir=exp,
        )
        t = threading.Thread(target=worker.run)
        t.start()
        time.sleep(0.25)
        stop.set()
        t.join(timeout=2.0)
    assert not error.is_set()
    lines = (exp.root / "scale.csv").read_text().splitlines()
    assert lines[0].split(";") == [
        "timestamp_utc",
        "elapsed_s",
        "phase",
        "combo_index",
        "set_speed_rpm",
        "set_frequency_hz",
        "set_amplitude_vpp",
        "weight_g",
    ]
    for line in lines[1:]:
        cols = line.split(";")
        assert cols[2] == "sweep"
        assert cols[3] == "1"
        assert cols[4] == "200"
        assert cols[5] == "20.0"
        assert cols[6] == "3.0"


def test_scale_worker_respects_log_interval(tmp_path: Path) -> None:
    state = ExperimentState()
    state.update(combo_index=1, set_speed_rpm=200, set_frequency_hz=20.0, set_amplitude_vpp=3.0)
    exp = ExperimentDirectory.create(base_dir=tmp_path, experiment_id="X")
    scale = FakeScale()
    stop = threading.Event()
    error = threading.Event()
    with scale:
        worker = ScaleWorker(
            scale=scale,
            state=state,
            stop_event=stop,
            error_event=error,
            log_interval_s=0.2,
            experiment_dir=exp,
        )
        t = threading.Thread(target=worker.run)
        t.start()
        time.sleep(0.5)
        stop.set()
        t.join(timeout=2.0)
    n_data = len((exp.root / "scale.csv").read_text().splitlines()) - 1
    assert 1 <= n_data <= 4
