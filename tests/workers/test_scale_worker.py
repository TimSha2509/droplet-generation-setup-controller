import threading
import time

from droplet_lab.devices.scale_fake import FakeScale
from droplet_lab.state import ExperimentState
from droplet_lab.storage import ExperimentDirectory
from droplet_lab.workers.scale_worker import ScaleWorker


def test_writes_scale_csv(tmp_path) -> None:
    state = ExperimentState()
    state.update(step_index=1, set_speed_rpm=200)
    scale = FakeScale()
    exp = ExperimentDirectory.create(base_dir=tmp_path, experiment_id="X")
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
        time.sleep(0.2)
        stop.set()
        t.join(timeout=2.0)
    assert not error.is_set()
    text = (exp.root / "scale.csv").read_text()
    assert "weight_g" in text
    assert text.count("\n") >= 3
