import threading
import time

from droplet_lab.devices.oscilloscope_fake import FakeOscilloscope
from droplet_lab.state import ExperimentState
from droplet_lab.storage import ExperimentDirectory
from droplet_lab.workers.scope_worker import ScopeWorker


def test_writes_oscilloscope_csv(tmp_path) -> None:
    state = ExperimentState()
    state.update(step_index=1, set_speed_rpm=200)
    scope = FakeOscilloscope(state=state)
    exp = ExperimentDirectory.create(base_dir=tmp_path, experiment_id="X")
    stop = threading.Event()
    error = threading.Event()

    with scope:
        worker = ScopeWorker(
            scope=scope,
            state=state,
            stop_event=stop,
            error_event=error,
            log_interval_s=0.05,
            vibrometer_factor_um_per_v=5280,
            experiment_dir=exp,
        )
        t = threading.Thread(target=worker.run)
        t.start()
        time.sleep(0.3)
        stop.set()
        t.join(timeout=2.0)

    assert not error.is_set()
    text = (exp.root / "oscilloscope.csv").read_text()
    assert "p2p_displacement_um" in text
    assert text.count("\n") >= 3


def test_p2p_displacement_computed_from_vpp(tmp_path) -> None:
    state = ExperimentState()
    state.update(step_index=1, set_speed_rpm=500)
    scope = FakeOscilloscope(state=state, noise_amplitude=0.0)
    exp = ExperimentDirectory.create(base_dir=tmp_path, experiment_id="X")
    stop = threading.Event()
    error = threading.Event()

    with scope:
        worker = ScopeWorker(
            scope=scope,
            state=state,
            stop_event=stop,
            error_event=error,
            log_interval_s=0.05,
            vibrometer_factor_um_per_v=1000.0,
            experiment_dir=exp,
        )
        t = threading.Thread(target=worker.run)
        t.start()
        time.sleep(0.15)
        stop.set()
        t.join(timeout=2.0)

    rows = (exp.root / "oscilloscope.csv").read_text().strip().splitlines()
    header, *data = [r.split(";") for r in rows]
    vpp_idx = header.index("vpp_v")
    p2p_idx = header.index("p2p_displacement_um")
    for r in data:
        if r[vpp_idx] and r[p2p_idx]:
            assert abs(float(r[p2p_idx]) - float(r[vpp_idx]) * 1000.0) < 1e-6
            return
    raise AssertionError("no row with both vpp and p2p found")
