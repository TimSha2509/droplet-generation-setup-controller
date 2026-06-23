from pathlib import Path

import pytest

from droplet_lab.config import DisplacementConfig
from droplet_lab.displacement import (
    CalibrationCurve,
    CalibrationMeasurement,
    CalibrationModel,
    VoltageLimitPoint,
    calibration_frequencies,
    filter_non_monotonic_measurements,
    load_calibration_model,
    load_voltage_limits_csv,
    resolve_displacement,
    safe_amplitude_limit_vpp,
    save_calibration_model,
    validate_calibration_model,
    voltage_steps,
)


def _model() -> CalibrationModel:
    return CalibrationModel(
        version=1,
        created_at_utc="2026-06-19T00:00:00Z",
        vibrometer_factor_um_per_v=1000.0,
        amplifier_gain=2.0,
        curves=[
            CalibrationCurve(
                frequency_hz=10.0,
                safe_max_amplitude_vpp=5.0,
                measurements=[
                    CalibrationMeasurement(1.0, 1.0, 1000.0, [1000.0]),
                    CalibrationMeasurement(3.0, 3.0, 3000.0, [3000.0]),
                ],
            ),
            CalibrationCurve(
                frequency_hz=20.0,
                safe_max_amplitude_vpp=4.0,
                measurements=[
                    CalibrationMeasurement(2.0, 1.0, 1000.0, [1000.0]),
                    CalibrationMeasurement(4.0, 2.0, 2000.0, [2000.0]),
                ],
            ),
        ],
    )


def test_calibration_frequency_grid() -> None:
    cfg = DisplacementConfig(
        calibration_start_hz=10, calibration_stop_hz=30, calibration_step_hz=10
    )
    assert calibration_frequencies(cfg) == [10.0, 20.0, 30.0]


def test_voltage_steps_are_positive_and_end_at_max() -> None:
    assert voltage_steps(6.0, 3) == [2.0, 4.0, 6.0]


def test_safe_limit_applies_amplifier_gain_and_global_cap() -> None:
    limits = [
        VoltageLimitPoint(10.0, 12.0),
        VoltageLimitPoint(20.0, 20.0),
    ]
    assert safe_amplitude_limit_vpp(10.0, limits=limits, amplifier_gain=2.0) == 6.0
    assert safe_amplitude_limit_vpp(20.0, limits=limits, amplifier_gain=2.0) == 9.5
    assert safe_amplitude_limit_vpp(15.0, limits=limits, amplifier_gain=2.0) == 8.0


def test_safe_limit_reports_frequency_outside_voltage_table() -> None:
    limits = [
        VoltageLimitPoint(10.7, 12.0),
        VoltageLimitPoint(20.0, 20.0),
    ]

    with pytest.raises(ValueError, match="voltage-limit frequency value 10"):
        safe_amplitude_limit_vpp(10.0, limits=limits, amplifier_gain=2.0)


def test_resolve_displacement_interpolates_within_and_between_curves() -> None:
    assert resolve_displacement(_model(), frequency_hz=10.0, target_displacement_um=2000.0) == 2.0
    assert resolve_displacement(_model(), frequency_hz=15.0, target_displacement_um=1500.0) == 2.25


def test_resolve_displacement_rejects_out_of_range_target() -> None:
    with pytest.raises(ValueError, match="outside range"):
        resolve_displacement(_model(), frequency_hz=10.0, target_displacement_um=5000.0)


def test_validate_model_rejects_non_monotonic_curve() -> None:
    model = CalibrationModel(
        version=1,
        created_at_utc="2026-06-19T00:00:00Z",
        vibrometer_factor_um_per_v=1000.0,
        amplifier_gain=2.0,
        curves=[
            CalibrationCurve(
                frequency_hz=10.0,
                safe_max_amplitude_vpp=5.0,
                measurements=[
                    CalibrationMeasurement(1.0, 1.0, 1000.0, [1000.0]),
                    CalibrationMeasurement(2.0, 0.9, 900.0, [900.0]),
                ],
            )
        ],
    )
    with pytest.raises(ValueError, match="2 Vpp measured 900 um after 1 Vpp measured 1000 um"):
        validate_calibration_model(model)


def test_filter_non_monotonic_measurements_keeps_increasing_envelope() -> None:
    model = CalibrationModel(
        version=1,
        created_at_utc="2026-06-19T00:00:00Z",
        vibrometer_factor_um_per_v=1000.0,
        amplifier_gain=2.0,
        curves=[
            CalibrationCurve(
                frequency_hz=60.7,
                safe_max_amplitude_vpp=5.0,
                measurements=[
                    CalibrationMeasurement(1.0, 1.0, 1000.0, [1000.0]),
                    CalibrationMeasurement(2.0, 0.9, 900.0, [900.0]),
                    CalibrationMeasurement(3.0, 1.5, 1500.0, [1500.0]),
                ],
            )
        ],
    )

    result = filter_non_monotonic_measurements(model)

    assert [m.set_amplitude_vpp for m in result.model.curves[0].measurements] == [1.0, 3.0]
    assert [m.set_amplitude_vpp for m in result.skipped_measurements] == [2.0]
    validate_calibration_model(result.model)


def test_save_and_load_calibration_model(tmp_path: Path) -> None:
    path = tmp_path / "model.json"
    save_calibration_model(_model(), path)
    loaded = load_calibration_model(path)
    assert loaded.curves[0].measurements[0].median_displacement_um == 1000.0


def test_load_voltage_limits_csv(tmp_path: Path) -> None:
    path = tmp_path / "limits.csv"
    path.write_text(
        "Frequency [Hz];max. Voltage [V]\n"
        "10.0;12.0\n"
        "20.0;14.0\n",
        encoding="utf-8",
    )

    assert load_voltage_limits_csv(path) == [
        VoltageLimitPoint(10.0, 12.0),
        VoltageLimitPoint(20.0, 14.0),
    ]


def test_load_voltage_limits_csv_accepts_decimal_comma(tmp_path: Path) -> None:
    path = tmp_path / "limits.csv"
    path.write_text(
        "Frequency [Hz];max. Voltage [V]\n"
        "10,0;12,5\n"
        "20,0;14,5\n",
        encoding="utf-8",
    )

    assert load_voltage_limits_csv(path) == [
        VoltageLimitPoint(10.0, 12.5),
        VoltageLimitPoint(20.0, 14.5),
    ]
