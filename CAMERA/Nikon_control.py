import json
import math
import os
import sys
import time
from datetime import datetime

import requests


SERVER_URL = "http://localhost:5513"


def timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def dcc_set_folder(folder_path: str):
    response = requests.get(
        SERVER_URL,
        params={
            "slc": "set",
            "param1": "session.folder",
            "param2": folder_path,
        },
        timeout=10,
    )
    response.raise_for_status()
    print(f"[CAMERA] DigiCamControl folder set to: {folder_path}")
    print(f"[CAMERA] Response: {response.text}")


def dcc_capture():
    response = requests.get(
        SERVER_URL,
        params={
            "slc": "capture",
            "param1": "",
            "param2": "",
        },
        timeout=10,
    )
    response.raise_for_status()


def load_metadata(metadata_path: str) -> dict:
    with open(metadata_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_metadata(metadata_path: str, metadata: dict):
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)


def compute_expected_images(duration_s: float, interval_s: float) -> int:
    if duration_s <= 0 or interval_s <= 0:
        return 0
    return int(math.floor((duration_s - 1e-9) / interval_s)) + 1


def main():
    if len(sys.argv) < 5:
        print(
            "Usage: python Nikon_control.py "
            "<output_folder> <image_interval_s> <imaging_duration_s> <metadata_json_path>"
        )
        sys.exit(1)

    output_folder = sys.argv[1]
    image_interval_s = float(sys.argv[2])
    imaging_duration_s = float(sys.argv[3])
    metadata_json_path = sys.argv[4]

    os.makedirs(output_folder, exist_ok=True)

    metadata = load_metadata(metadata_json_path)
    metadata["camera_script_start_time"] = timestamp()
    metadata["camera_output_folder"] = output_folder
    metadata["camera_interval_s"] = image_interval_s
    metadata["camera_planned_duration_s"] = imaging_duration_s
    metadata["expected_image_count"] = compute_expected_images(imaging_duration_s, image_interval_s)
    metadata["camera_status"] = "starting"
    save_metadata(metadata_json_path, metadata)

    print(f"[CAMERA] Output folder: {output_folder}")
    print(f"[CAMERA] Interval: {image_interval_s} s")
    print(f"[CAMERA] Duration: {imaging_duration_s} s")

    try:
        dcc_set_folder(output_folder)
        metadata["camera_folder_set_time"] = timestamp()
        metadata["camera_status"] = "running"
        save_metadata(metadata_json_path, metadata)

        start_time = time.time()
        next_capture_time = start_time
        capture_count = 0
        first_capture_done = False

        while True:
            now = time.time()
            elapsed = now - start_time

            if elapsed > imaging_duration_s:
                break

            if now >= next_capture_time:
                dcc_capture()
                capture_count += 1

                if not first_capture_done:
                    metadata["camera_first_capture_time"] = timestamp()
                    first_capture_done = True

                metadata["camera_last_capture_time"] = timestamp()
                metadata["actual_image_count_so_far"] = capture_count
                save_metadata(metadata_json_path, metadata)

                print(f"[CAMERA] Captured image {capture_count}")
                next_capture_time += image_interval_s
            else:
                time.sleep(0.02)

        latency_tolerance_s = float(metadata.get("camera_latency_tolerance_s", 0.0))
        if latency_tolerance_s > 0:
            print(f"[CAMERA] Waiting {latency_tolerance_s} s latency tolerance...")
            time.sleep(latency_tolerance_s)

        metadata["camera_script_end_time"] = timestamp()
        metadata["actual_image_count"] = capture_count
        metadata["camera_status"] = "completed"
        save_metadata(metadata_json_path, metadata)

        print(f"[CAMERA] Capture session complete. Images triggered: {capture_count}")

    except Exception as e:
        metadata["camera_script_end_time"] = timestamp()
        metadata["camera_status"] = "failed"
        metadata["camera_error"] = str(e)
        save_metadata(metadata_json_path, metadata)
        print(f"[CAMERA][ERROR] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()