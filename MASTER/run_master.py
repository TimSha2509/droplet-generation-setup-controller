import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime


# =========================
# EXPERIMENT SETTINGS
# =========================
EXPERIMENT_ID = "HPMC_Test_01"
NOZZLE_ID = "1mm_A"

FREQUENCY_SET = 200          # Hz
VOLTAGE_SET = 5              # V
VIBROMETER_FACTOR = 5280     # um/V

RAMP_PROFILE = [
    (200, 30),
    (250, 30),
    (300, 60),
    (350, 60),
    (400, 120),
]

STABILIZATION_DELAY_S = 10
IMAGE_INTERVAL_S = 5
CAMERA_LATENCY_TOLERANCE_S = 1.0
MAX_SPEED = 1000

# Set your oscilloscope VISA resource here
OSC_VISA_RESOURCE = "USB0::0x2A8D::0x1778::MY55440264::0::INSTR"

BASE_DATA_DIR = r"W:\PROMOTION_SHARIFSOLTANI_VERKAPSELUNG_DFG_TH1817_9_1_MT\PYTHON\Project_files\DATA"

PUMP_SCRIPT = r"W:\PROMOTION_SHARIFSOLTANI_VERKAPSELUNG_DFG_TH1817_9_1_MT\PYTHON\Project_files\Pump\pump_logger.py"
CAMERA_SCRIPT = r"W:\PROMOTION_SHARIFSOLTANI_VERKAPSELUNG_DFG_TH1817_9_1_MT\PYTHON\Project_files\CAMERA\Nikon_control.py"
OSCILLOSCOPE_SCRIPT = r"W:\PROMOTION_SHARIFSOLTANI_VERKAPSELUNG_DFG_TH1817_9_1_MT\PYTHON\Project_files\OSCILLOSCOPE\Oscilloscope_logger.py"

PUMP_COMMAND_DIR = os.path.join(BASE_DATA_DIR, "PUMP")
PUMP_COMMAND_FILE = os.path.join(PUMP_COMMAND_DIR, "pump_command.txt")


stop_requested = False


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def sanitize_filename(text: str) -> str:
    invalid = '<>:"/\\|?*'
    for ch in invalid:
        text = text.replace(ch, "_")
    return text.strip().replace(" ", "_")


def experiment_folder_name():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{ts}_{sanitize_filename(EXPERIMENT_ID)}"


def make_step_folder_name(step_index: int, speed: int) -> str:
    return f"Step{step_index:02d}_{speed}rpm"


def write_json(path: str, payload: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def update_json(path: str, updates: dict):
    payload = read_json(path)
    payload.update(updates)
    write_json(path, payload)


def write_command(command: str):
    os.makedirs(PUMP_COMMAND_DIR, exist_ok=True)
    with open(PUMP_COMMAND_FILE, "w", encoding="utf-8") as f:
        f.write(command)


def start_pump_logger(experiment_id: str, nozzle_id: str, initial_speed: int):
    cmd = [
        sys.executable,
        PUMP_SCRIPT,
        experiment_id,
        nozzle_id,
        str(initial_speed),
    ]
    return subprocess.Popen(cmd)


def start_oscilloscope_logger(experiment_root: str, state_json_path: str):
    cmd = [
        sys.executable,
        OSCILLOSCOPE_SCRIPT,
        experiment_root,
        OSC_VISA_RESOURCE,
        EXPERIMENT_ID,
        NOZZLE_ID,
        str(FREQUENCY_SET),
        str(VOLTAGE_SET),
        str(VIBROMETER_FACTOR),
        state_json_path,
    ]
    return subprocess.Popen(cmd)


def stop_listener():
    global stop_requested
    while not stop_requested:
        command = input("> ").strip().lower()
        if command == "stop":
            stop_requested = True
            print("Stop requested by user.")
            break


def wait_with_stop(seconds: float) -> bool:
    end_time = time.time() + seconds
    while time.time() < end_time:
        if stop_requested:
            return True
        time.sleep(0.1)
    return False


def create_experiment_root() -> str:
    root = os.path.join(BASE_DATA_DIR, experiment_folder_name())
    os.makedirs(root, exist_ok=True)
    return root


def create_experiment_metadata(experiment_root: str):
    path = os.path.join(experiment_root, "experiment_metadata.json")
    payload = {
        "experiment_id": EXPERIMENT_ID,
        "nozzle_id": NOZZLE_ID,
        "frequency_set_hz": FREQUENCY_SET,
        "voltage_set_v": VOLTAGE_SET,
        "vibrometer_factor_um_per_v": VIBROMETER_FACTOR,
        "experiment_root": experiment_root,
        "experiment_start_time": now_str(),
        "ramp_profile": RAMP_PROFILE,
        "stabilization_delay_s": STABILIZATION_DELAY_S,
        "image_interval_s": IMAGE_INTERVAL_S,
        "camera_latency_tolerance_s": CAMERA_LATENCY_TOLERANCE_S,
        "max_speed": MAX_SPEED,
        "osc_visa_resource": OSC_VISA_RESOURCE,
        "pump_script": PUMP_SCRIPT,
        "camera_script": CAMERA_SCRIPT,
        "oscilloscope_script": OSCILLOSCOPE_SCRIPT,
        "status": "running",
    }
    write_json(path, payload)
    return path


def create_state_json(experiment_root: str, initial_speed: int):
    path = os.path.join(experiment_root, "experiment_state.json")
    payload = {
        "timestamp": now_str(),
        "step_index": 1,
        "set_speed_rpm": initial_speed,
    }
    write_json(path, payload)
    return path


def update_state_json(state_json_path: str, step_index: int, set_speed_rpm: int):
    payload = {
        "timestamp": now_str(),
        "step_index": step_index,
        "set_speed_rpm": set_speed_rpm,
    }
    write_json(state_json_path, payload)


def create_step_metadata(
    step_folder: str,
    step_index: int,
    speed: int,
    hold_time: int,
    imaging_duration: float,
):
    metadata_path = os.path.join(step_folder, "metadata.json")
    payload = {
        "experiment_id": EXPERIMENT_ID,
        "nozzle_id": NOZZLE_ID,
        "frequency_set_hz": FREQUENCY_SET,
        "voltage_set_v": VOLTAGE_SET,
        "vibrometer_factor_um_per_v": VIBROMETER_FACTOR,
        "step_index": step_index,
        "step_folder": step_folder,
        "set_speed_rpm": speed,
        "hold_time_s": hold_time,
        "stabilization_delay_s": STABILIZATION_DELAY_S,
        "image_interval_s": IMAGE_INTERVAL_S,
        "imaging_duration_s": imaging_duration,
        "camera_latency_tolerance_s": CAMERA_LATENCY_TOLERANCE_S,
        "step_start_time": now_str(),
        "step_status": "planned",
        "camera_status": "not_started",
    }
    write_json(metadata_path, payload)
    return metadata_path


def launch_camera(step_folder: str, metadata_path: str, imaging_duration: float):
    cmd = [
        sys.executable,
        CAMERA_SCRIPT,
        step_folder,
        str(IMAGE_INTERVAL_S),
        str(imaging_duration),
        metadata_path,
    ]
    return subprocess.Popen(cmd)


def terminate_camera(camera_process, metadata_path):
    if camera_process is None:
        return

    if camera_process.poll() is None:
        camera_process.terminate()
        try:
            camera_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            camera_process.kill()
            camera_process.wait()

    if metadata_path and os.path.exists(metadata_path):
        update_json(
            metadata_path,
            {
                "camera_status": "aborted",
                "camera_script_end_time": now_str(),
            },
        )


def stop_oscilloscope_logger(experiment_root: str, osc_process):
    stop_file = os.path.join(experiment_root, "oscilloscope_stop.txt")
    with open(stop_file, "w", encoding="utf-8") as f:
        f.write("STOP")

    if osc_process is not None:
        try:
            osc_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            osc_process.kill()
            osc_process.wait()


def main():
    global stop_requested

    if not RAMP_PROFILE:
        print("RAMP_PROFILE is empty.")
        return

    for speed, hold_time in RAMP_PROFILE:
        if speed < 0:
            print(f"Invalid negative speed: {speed}")
            return
        if speed > MAX_SPEED:
            print(f"Speed {speed} exceeds MAX_SPEED={MAX_SPEED}")
            return
        if hold_time <= 0:
            print(f"Invalid hold time: {hold_time}")
            return

    os.makedirs(PUMP_COMMAND_DIR, exist_ok=True)
    if os.path.exists(PUMP_COMMAND_FILE):
        os.remove(PUMP_COMMAND_FILE)

    experiment_root = create_experiment_root()
    experiment_metadata_path = create_experiment_metadata(experiment_root)
    state_json_path = create_state_json(experiment_root, RAMP_PROFILE[0][0])

    print("Starting experiment...")
    print(f"Experiment_ID  : {EXPERIMENT_ID}")
    print(f"Nozzle_ID      : {NOZZLE_ID}")
    print(f"FREQUENCY_SET  : {FREQUENCY_SET} Hz")
    print(f"VOLTAGE_SET    : {VOLTAGE_SET} V")
    print(f"VIBROMETER_FACTOR: {VIBROMETER_FACTOR} um/V")
    print(f"Experiment dir : {experiment_root}")
    print("Ramp profile:")
    for idx, (speed, hold_time) in enumerate(RAMP_PROFILE, start=1):
        print(f"  Step {idx}: {speed} rpm for {hold_time} s")
    print()
    print("Type 'stop' at any time to stop the experiment.")
    print()

    listener_thread = threading.Thread(target=stop_listener, daemon=True)
    listener_thread.start()

    pump_process = start_pump_logger(EXPERIMENT_ID, NOZZLE_ID, RAMP_PROFILE[0][0])
    osc_process = start_oscilloscope_logger(experiment_root, state_json_path)
    active_camera_process = None
    active_metadata_path = None

    try:
        time.sleep(3)

        for step_index, (speed, hold_time) in enumerate(RAMP_PROFILE, start=1):
            if stop_requested:
                break

            update_state_json(state_json_path, step_index, speed)

            if step_index > 1:
                print(f"[MASTER] Setting pump speed to {speed} rpm")
                write_command(f"SET_SPEED:{speed}")
                time.sleep(1)

            step_folder = os.path.join(
                experiment_root,
                make_step_folder_name(step_index, speed)
            )
            os.makedirs(step_folder, exist_ok=True)

            imaging_duration = max(0, hold_time - STABILIZATION_DELAY_S)

            metadata_path = create_step_metadata(
                step_folder=step_folder,
                step_index=step_index,
                speed=speed,
                hold_time=hold_time,
                imaging_duration=imaging_duration,
            )
            active_metadata_path = metadata_path

            print(f"[MASTER] Step {step_index}: {speed} rpm")
            print(f"[MASTER] Step folder: {step_folder}")
            print(f"[MASTER] Stabilizing for {STABILIZATION_DELAY_S} s")

            update_json(metadata_path, {"step_status": "stabilizing"})

            if wait_with_stop(STABILIZATION_DELAY_S):
                break

            if imaging_duration <= 0:
                print(f"[MASTER] Step {step_index}: no imaging, hold time too short.")
                update_json(
                    metadata_path,
                    {
                        "step_status": "completed_no_imaging",
                        "step_end_time": now_str(),
                    },
                )
                continue

            print(
                f"[MASTER] Starting camera for {imaging_duration} s, "
                f"interval {IMAGE_INTERVAL_S} s"
            )

            update_json(
                metadata_path,
                {
                    "step_status": "imaging",
                    "imaging_start_time_planned": now_str(),
                },
            )

            active_camera_process = launch_camera(step_folder, metadata_path, imaging_duration)

            end_time = time.time() + imaging_duration + CAMERA_LATENCY_TOLERANCE_S + 5.0
            while True:
                if stop_requested:
                    break

                if active_camera_process.poll() is not None:
                    break

                if time.time() > end_time:
                    print("[MASTER] Camera process timeout reached, terminating.")
                    terminate_camera(active_camera_process, metadata_path)
                    break

                time.sleep(0.1)

            if stop_requested:
                break

            camera_rc = active_camera_process.poll()
            if camera_rc is None:
                terminate_camera(active_camera_process, metadata_path)
                update_json(
                    metadata_path,
                    {
                        "step_status": "camera_timeout",
                        "step_end_time": now_str(),
                    },
                )
            elif camera_rc == 0:
                update_json(
                    metadata_path,
                    {
                        "step_status": "completed",
                        "step_end_time": now_str(),
                    },
                )
            else:
                update_json(
                    metadata_path,
                    {
                        "step_status": "camera_failed",
                        "step_end_time": now_str(),
                    },
                )
                print(f"[MASTER] Camera process failed in step {step_index}. Stopping experiment.")
                stop_requested = True
                break

            active_camera_process = None
            active_metadata_path = None

        if stop_requested:
            print("[MASTER] Stopping experiment...")
            if active_camera_process is not None:
                terminate_camera(active_camera_process, active_metadata_path)

            if active_metadata_path and os.path.exists(active_metadata_path):
                update_json(
                    active_metadata_path,
                    {
                        "step_status": "aborted",
                        "step_end_time": now_str(),
                    },
                )

            write_command("STOP")
            pump_process.wait()

            stop_oscilloscope_logger(experiment_root, osc_process)

            update_json(
                experiment_metadata_path,
                {
                    "experiment_end_time": now_str(),
                    "status": "aborted",
                },
            )
            print("[MASTER] Experiment aborted.")

        else:
            print("[MASTER] Ramp profile finished. Stopping pump...")
            write_command("STOP")
            pump_process.wait()

            stop_oscilloscope_logger(experiment_root, osc_process)

            update_json(
                experiment_metadata_path,
                {
                    "experiment_end_time": now_str(),
                    "status": "completed",
                },
            )
            print("[MASTER] Experiment completed.")

    except KeyboardInterrupt:
        print("\n[MASTER] Keyboard interrupt detected. Stopping experiment...")
        stop_requested = True

        if active_camera_process is not None:
            terminate_camera(active_camera_process, active_metadata_path)

        if active_metadata_path and os.path.exists(active_metadata_path):
            update_json(
                active_metadata_path,
                {
                    "step_status": "aborted",
                    "step_end_time": now_str(),
                },
            )

        write_command("STOP")
        pump_process.wait()
        stop_oscilloscope_logger(experiment_root, osc_process)

        update_json(
            experiment_metadata_path,
            {
                "experiment_end_time": now_str(),
                "status": "aborted_keyboard_interrupt",
            },
        )
        print("[MASTER] Experiment stopped safely.")


if __name__ == "__main__":
    main()