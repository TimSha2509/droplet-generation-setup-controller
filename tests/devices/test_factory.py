from droplet_lab.config import (
    CameraConfig,
    OscilloscopeConfig,
    PumpConfig,
    ScaleConfig,
)
from droplet_lab.devices import (
    build_camera,
    build_oscilloscope,
    build_pump,
    build_scale,
)
from droplet_lab.devices.camera_fake import FakeCamera
from droplet_lab.devices.oscilloscope_fake import FakeOscilloscope
from droplet_lab.devices.pump_fake import FakePump
from droplet_lab.devices.scale_fake import FakeScale
from droplet_lab.state import ExperimentState


def test_simulate_returns_fakes() -> None:
    pump = build_pump(PumpConfig(port="COM3"), simulate=True)
    scope = build_oscilloscope(
        OscilloscopeConfig(visa_resource="USB"),
        state=ExperimentState(),
        simulate=True,
    )
    cam = build_camera(CameraConfig(), simulate=True)
    scale = build_scale(ScaleConfig(enabled=True, port="COM5"), simulate=True)
    assert isinstance(pump, FakePump)
    assert isinstance(scope, FakeOscilloscope)
    assert isinstance(cam, FakeCamera)
    assert isinstance(scale, FakeScale)


def test_real_returns_real_classes() -> None:
    from droplet_lab.devices.camera_digicam import DigiCamCamera
    from droplet_lab.devices.oscilloscope_keysight import KeysightOscilloscope
    from droplet_lab.devices.pump_mzr7245 import MZR7245Pump
    from droplet_lab.devices.scale_sartorius import SartoriusScale

    pump = build_pump(PumpConfig(port="COM3"), simulate=False)
    scope = build_oscilloscope(
        OscilloscopeConfig(visa_resource="USB"),
        state=ExperimentState(),
        simulate=False,
    )
    cam = build_camera(CameraConfig(), simulate=False)
    scale = build_scale(ScaleConfig(enabled=True, port="COM5"), simulate=False)
    assert isinstance(pump, MZR7245Pump)
    assert isinstance(scope, KeysightOscilloscope)
    assert isinstance(cam, DigiCamCamera)
    assert isinstance(scale, SartoriusScale)
