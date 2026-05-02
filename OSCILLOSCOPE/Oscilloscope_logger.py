import csv
import json
import os
import sys
import time
from datetime import datetime

import pyvisa


LOG_INTERVAL_S = 15.0


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_json(path: str, default=None):
    if default is None:
        default = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path: str, payload: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def safe_float(value, default=None):
    try:
        return float(str(value).strip())
    except Exception:
        return default


def query_float(scope, command: str, default=None):
    try:
        return safe_float(scope.query(command), default=default)
    except Exception:
        return default


def main():
    if len(sys.argv) < 9:
        print(
            "Usage: python oscilloscope_logger.py "
            "<experiment_root> <visa_resource> <experiment_id> <nozzle_id> "
            "<frequency_set_hz> <voltage_set_v> <vibrometer_factor_um_per_v> "
            "<state_json_path>"
        )
        sys.exit(1)

    experiment_root = sys.argv[1]
    visa_resource = sys.argv[2]
    experiment_id = sys.argv[3]
    nozzle_id = sys.argv[4]
    frequency_set_hz = float(sys.argv[5])
    voltage_set_v = float(sys.argv[6])
    vibrometer_factor_um_per_v = float(sys.argv[7])
    state_json_path = sys.argv[8]

    os.makedirs(experiment_root, exist_ok=True)

    stop_file = os.path.join(experiment_root, "oscilloscope_stop.txt")
    metadata_path = os.path.join(experiment_root, "oscilloscope_metadata.json")
    csv_path = os.path.join(experiment_root, "oscilloscope_log.csv")

    if os.path.exists(stop_file):
        os.remove(stop_file)

    metadata = {
        "experiment_id": experiment_id,
        "nozzle_id": nozzle_id,
        "frequency_set_hz": frequency_set_hz,
        "voltage_set_v": voltage_set_v,
        "vibrometer_factor_um_per_v": vibrometer_factor_um_per_v,
        "visa_resource": visa_resource,
        "log_interval_s": LOG_INTERVAL_S,
        "start_time": now_str(),
        "status": "starting",
    }
    write_json(metadata_path, metadata)

    rm = None
    scope = None
    csvfile = None

    try:
        rm = pyvisa.ResourceManager()
        scope = rm.open_resource(visa_resource)

        # Conservative defaults for text SCPI I/O
        scope.timeout = 5000
        scope.write_termination = "\n"
        scope.read_termination = "\n"

        idn = scope.query("*IDN?").strip()
        metadata["scope_idn"] = idn
        metadata["status"] = "running"
        write_json(metadata_path, metadata)

        print(f"[SCOPE] Connected to: {idn}")
        print(f"[SCOPE] Logging to: {csv_path}")

        csvfile = open(csv_path, mode="w", newline="", encoding="utf-8")
        writer = csv.writer(csvfile, delimiter=";")
        writer.writerow([
            "timestamp",
            "elapsed_s",
            "experiment_id",
            "nozzle_id",
            "frequency_set_hz",
            "voltage_set_v",
            "vibrometer_factor_um_per_v",
            "step_index",
            "set_speed_rpm",
            "frequency_measured",
            "vibrometer_output_voltage",
            "p2p_displacement_um",
            "channel_2_vrms_dc",
            "channel_3_vrms_dc",
        ])
        csvfile.flush()

        start_time = time.time()

        while True:
            if os.path.exists(stop_file):
                print("[SCOPE] Stop signal detected.")
                break

            state = read_json(
                state_json_path,
                default={"step_index": None, "set_speed_rpm": None}
            )

            step_index = state.get("step_index")
            set_speed_rpm = state.get("set_speed_rpm")

            frequency_measured = query_float(scope, ":MEASure:FREQuency? CHANnel1")
            vibrometer_output_voltage = query_float(scope, ":MEASure:VPP? CHANnel1")
            channel_2_vrms_dc = query_float(scope, ":MEASure:VRMS? DISPlay,DC,CHANnel2")
            channel_3_vrms_dc = query_float(scope, ":MEASure:VRMS? DISPlay,DC,CHANnel3")

            p2p_displacement_um = None
            if vibrometer_output_voltage is not None:
                p2p_displacement_um = vibrometer_output_voltage * vibrometer_factor_um_per_v

            writer.writerow([
                now_str(),
                round(time.time() - start_time, 3),
                experiment_id,
                nozzle_id,
                frequency_set_hz,
                voltage_set_v,
                vibrometer_factor_um_per_v,
                step_index,
                set_speed_rpm,
                frequency_measured,
                vibrometer_output_voltage,
                p2p_displacement_um,
                channel_2_vrms_dc,
                channel_3_vrms_dc,
            ])
            csvfile.flush()

            end_time = time.time() + LOG_INTERVAL_S
            while time.time() < end_time:
                if os.path.exists(stop_file):
                    break
                time.sleep(0.1)

    except Exception as e:
        metadata["status"] = "failed"
        metadata["error"] = str(e)
        metadata["end_time"] = now_str()
        write_json(metadata_path, metadata)
        print(f"[SCOPE][ERROR] {e}")
        sys.exit(1)

    finally:
        metadata["status"] = "completed"
        metadata["end_time"] = now_str()
        write_json(metadata_path, metadata)

        if csvfile is not None:
            csvfile.close()

        try:
            if scope is not None:
                scope.close()
        except Exception:
            pass

        try:
            if rm is not None:
                rm.close()
        except Exception:
            pass

        if os.path.exists(stop_file):
            os.remove(stop_file)

        print("[SCOPE] Logger stopped safely.")


if __name__ == "__main__":
    main()