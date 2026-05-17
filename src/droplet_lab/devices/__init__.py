"""Hardware device abstractions and factories."""

from droplet_lab.config import (
    CameraConfig,
    FunctionGeneratorConfig,
    OscilloscopeConfig,
    PumpConfig,
    ScaleConfig,
)
from droplet_lab.devices.base import (
    Camera,
    FunctionGenerator,
    Oscilloscope,
    Pump,
    Scale,
    ScopeMeasurement,
)
from droplet_lab.devices.camera_digicam import DigiCamCamera
from droplet_lab.devices.camera_fake import FakeCamera
from droplet_lab.devices.function_generator_fake import FakeFunctionGenerator
from droplet_lab.devices.function_generator_psg9080 import PSG9080Generator
from droplet_lab.devices.oscilloscope_fake import FakeOscilloscope
from droplet_lab.devices.oscilloscope_keysight import KeysightOscilloscope
from droplet_lab.devices.pump_fake import FakePump
from droplet_lab.devices.pump_mzr7245 import MZR7245Pump
from droplet_lab.devices.scale_fake import FakeScale
from droplet_lab.devices.scale_sartorius import SartoriusScale
from droplet_lab.state import ExperimentState

__all__ = [
    "Camera",
    "FunctionGenerator",
    "Oscilloscope",
    "Pump",
    "Scale",
    "ScopeMeasurement",
    "build_camera",
    "build_function_generator",
    "build_oscilloscope",
    "build_pump",
    "build_scale",
]


def build_pump(cfg: PumpConfig, *, simulate: bool) -> Pump:
    if simulate:
        return FakePump()
    return MZR7245Pump(port=cfg.port, baudrate=cfg.baudrate)


def build_oscilloscope(
    cfg: OscilloscopeConfig,
    *,
    state: ExperimentState,
    simulate: bool,
) -> Oscilloscope:
    if simulate:
        return FakeOscilloscope(state=state)
    return KeysightOscilloscope(visa_resource=cfg.visa_resource, timeout_ms=cfg.timeout_ms)


def build_camera(cfg: CameraConfig, *, simulate: bool) -> Camera:
    if simulate:
        return FakeCamera()
    return DigiCamCamera(url=cfg.digicam_url, request_timeout_s=cfg.request_timeout_s)


def build_function_generator(cfg: FunctionGeneratorConfig, *, simulate: bool) -> FunctionGenerator:
    if simulate:
        return FakeFunctionGenerator()
    return PSG9080Generator(port=cfg.port, channel=cfg.channel, baudrate=cfg.baudrate)


def build_scale(cfg: ScaleConfig, *, simulate: bool) -> Scale:
    if simulate:
        return FakeScale()
    if cfg.port is None:
        raise ValueError("ScaleConfig.port must be set when simulate=False")
    return SartoriusScale(port=cfg.port, baudrate=cfg.baudrate)
