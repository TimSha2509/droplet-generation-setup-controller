import csv
import os
import sys
import time
from datetime import datetime

import serial


PORT = "COM3"
BAUDRATE = 9600
LOG_INTERVAL = 5

SAVE_DIR = r"W:\PROMOTION_SHARIFSOLTANI_VERKAPSELUNG_DFG_TH1817_9_1_MT\PYTHON\Project_files\DATA\PUMP"
COMMAND_FILE = os.path.join(SAVE_DIR, "pump_command.txt")


class MZR7245Pump:
    def __init__(self, port=PORT, baudrate=BAUDRATE, timeout=1.0):
        self.ser = serial.Serial(port=port, baudrate=baudrate, timeout=timeout)
        time.sleep(2)

    def close(self):
        if self.ser.is_open:
            self.ser.close()

    def cmd(self, command: str, pause: float = 0.2):
        self.ser.reset_input_buffer()
        self.ser.write((command + "\r").encode("ascii"))
        self.ser.flush()
        time.sleep(pause)
        reply = self.ser.read_all().decode("ascii", errors="replace").strip()
        return reply if reply else None

    def set_speed(self, speed_rpm: int):
        self.cmd(f"V{int(speed_rpm)}")

    def stop(self):
        self.cmd("V0")

    def get_temperature(self):
        return self.cmd("TEM")

    def get_actual_speed(self):
        return self.cmd("GN")

    def get_target_speed(self):
        return self.cmd("GV")


def safe_int(value, default=None):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def sanitize_filename(text: str) -> str:
    invalid = '<>:"/\\|?*'
    for ch in invalid:
        text = text.replace(ch, "_")
    return text.strip().replace(" ", "_")


def create_csv_file(experiment_id, nozzle_id, initial_speed):
    os.makedirs(SAVE_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = (
        f"{timestamp}_"
        f"{sanitize_filename(experiment_id)}_"
        f"{sanitize_filename(nozzle_id)}_"
        f"SetPumpSpeed{initial_speed}.csv"
    )

    filepath = os.path.join(SAVE_DIR, filename)

    csvfile = open(filepath, mode="a", newline="", encoding="utf-8")
    writer = csv.writer(csvfile, delimiter=";")

    writer.writerow([
        "timestamp",
        "experiment_id",
        "nozzle_id",
        "set_speed_rpm",
        "actual_speed_rpm",
        "temperature_C",
    ])
    csvfile.flush()

    return csvfile, writer, filepath


def read_command():
    if not os.path.exists(COMMAND_FILE):
        return None

    try:
        with open(COMMAND_FILE, "r", encoding="utf-8") as f:
            command = f.read().strip()
        os.remove(COMMAND_FILE)
        return command
    except Exception:
        return None


def main():
    if len(sys.argv) < 4:
        print("Usage: python pump_logger.py <Experiment_ID> <Nozzle_ID> <InitialSpeed>")
        sys.exit(1)

    experiment_id = sys.argv[1]
    nozzle_id = sys.argv[2]
    current_set_speed = int(sys.argv[3])

    if os.path.exists(COMMAND_FILE):
        os.remove(COMMAND_FILE)

    pump = MZR7245Pump()
    csvfile, writer, filepath = create_csv_file(experiment_id, nozzle_id, current_set_speed)

    print(f"Logging to: {filepath}")
    print(f"Starting pump at {current_set_speed} rpm...")

    try:
        pump.set_speed(current_set_speed)

        last_log_time = 0.0

        while True:
            command = read_command()
            if command:
                if command.upper() == "STOP":
                    print("External stop signal detected.")
                    break

                if command.upper().startswith("SET_SPEED:"):
                    try:
                        new_speed = int(command.split(":", 1)[1])
                        pump.set_speed(new_speed)
                        current_set_speed = new_speed
                        print(f"Pump speed changed to {current_set_speed} rpm")
                    except ValueError:
                        print(f"Ignoring invalid speed command: {command}")

            now = time.time()
            if now - last_log_time >= LOG_INTERVAL:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                temperature = safe_int(pump.get_temperature())
                actual_speed = safe_int(pump.get_actual_speed())
                target_speed = safe_int(pump.get_target_speed(), default=current_set_speed)

                writer.writerow([
                    timestamp,
                    experiment_id,
                    nozzle_id,
                    target_speed,
                    actual_speed,
                    temperature,
                ])
                csvfile.flush()
                last_log_time = now

            time.sleep(0.1)

    finally:
        pump.stop()
        pump.close()
        csvfile.close()

        if os.path.exists(COMMAND_FILE):
            os.remove(COMMAND_FILE)

        print("Pump stopped safely.")


if __name__ == "__main__":
    main()