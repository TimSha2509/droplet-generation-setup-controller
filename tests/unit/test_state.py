# mypy: disable-error-code="comparison-overlap"
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
    assert state.step_index is None
    assert state.set_speed_rpm is None


def test_experiment_state_update_is_thread_safe() -> None:
    import threading

    state = ExperimentState()

    def writer(start: int) -> None:
        for i in range(start, start + 100):
            state.update(step_index=i, set_speed_rpm=i * 10)

    threads = [threading.Thread(target=writer, args=(i * 1000,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    snapshot = state.snapshot()
    assert snapshot.step_index is not None
    assert snapshot.set_speed_rpm is not None
    assert snapshot.set_speed_rpm == snapshot.step_index * 10
