# mypy: disable-error-code="comparison-overlap"
import threading

from droplet_lab.state import (
    CameraStatus,
    ExperimentState,
    ExperimentStatus,
    StepStatus,
)


def test_status_enums_have_string_values() -> None:
    assert ExperimentStatus.RUNNING == "running"
    assert ExperimentStatus.COMPLETED == "completed"
    assert ExperimentStatus.ABORTED == "aborted"
    assert ExperimentStatus.FAILED == "failed"

    assert StepStatus.PLANNED == "planned"
    assert StepStatus.STABILIZING == "stabilizing"
    assert StepStatus.IMAGING == "imaging"
    assert StepStatus.COMPLETED == "completed"
    assert StepStatus.COMPLETED_NO_IMAGING == "completed_no_imaging"
    assert StepStatus.CAMERA_TIMEOUT == "camera_timeout"
    assert StepStatus.CAMERA_FAILED == "camera_failed"
    assert StepStatus.ABORTED == "aborted"

    assert CameraStatus.NOT_STARTED == "not_started"
    assert CameraStatus.STARTING == "starting"
    assert CameraStatus.RUNNING == "running"
    assert CameraStatus.COMPLETED == "completed"
    assert CameraStatus.FAILED == "failed"
    assert CameraStatus.ABORTED == "aborted"


def test_experiment_state_initial_values() -> None:
    state = ExperimentState()
    assert state.combo_index is None
    assert state.set_speed_rpm is None
    assert state.set_frequency_hz is None
    assert state.set_amplitude_vpp is None


def test_experiment_state_update_round_trips_all_fields() -> None:
    state = ExperimentState()
    state.update(combo_index=7, set_speed_rpm=800, set_frequency_hz=25.0, set_amplitude_vpp=5.0)
    snap = state.snapshot()
    assert snap.combo_index == 7
    assert snap.set_speed_rpm == 800
    assert snap.set_frequency_hz == 25.0
    assert snap.set_amplitude_vpp == 5.0


def test_experiment_state_update_is_thread_safe() -> None:
    state = ExperimentState()

    def writer(start: int) -> None:
        for i in range(start, start + 100):
            state.update(
                combo_index=i,
                set_speed_rpm=i * 10,
                set_frequency_hz=float(i),
                set_amplitude_vpp=float(i) / 2.0,
            )

    threads = [threading.Thread(target=writer, args=(i * 1000,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    snap = state.snapshot()
    assert snap.combo_index is not None
    assert snap.set_speed_rpm == snap.combo_index * 10
    assert snap.set_frequency_hz == float(snap.combo_index)
