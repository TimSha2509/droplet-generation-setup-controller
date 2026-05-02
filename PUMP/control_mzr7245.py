import csv
import os
import threading
import time
from datetime import datetime

import serial


# =========================
# EXPERIMENT SETTINGS
# =========================
PORT = "COM3"
BAUDRATE = 9600
PUMP_SPEED = 300          # rpm
LOG_INTERVAL = 5          # seconds

SAVE_DIR = r"W:\PROMOTION_SHARIFSOLTANI_VERKAPSELUNG_DFG_TH1817_9_1_MT\PYTHON\Project_files\DATA\PUMP"


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

    def get_target_speed(self):
        return self.cmd("GV")

    def get_actual_speed(self):
        return self.cmd("GN")


def safe_int(value, default=None):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def create_csv_file():
    os.makedirs(SAVE_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_SetPumpSpeed{PUMP_SPEED}.csv"

    filepath = os.path.join(SAVE_DIR, filename)
    file_exists = os.path.exists(filepath)

    csvfile = open(filepath, mode="a", newline="", encoding="utf-8")
    writer = csv.writer(csvfile, delimiter=";")

    if not file_exists:
        writer.writerow([
            "timestamp",
            "temperature_C",
            "set_speed_rpm",
            "actual_speed_rpm",
        ])
        csvfile.flush()

    return csvfile, writer, filepath


def logging_worker(pump: MZR7245Pump, stop_event: threading.Event):
    csvfile, writer, filepath = create_csv_file()
    print(f"Logging to: {filepath}")

    try:
        while not stop_event.is_set():
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            temperature = safe_int(pump.get_temperature())
            target_speed = safe_int(
                pump.get_target_speed(),
                default=PUMP_SPEED
            )
            actual_speed = safe_int(pump.get_actual_speed())

            writer.writerow([
                timestamp,
                temperature,
                target_speed,
                actual_speed,
            ])
            csvfile.flush()

            for _ in range(int(LOG_INTERVAL * 10)):
                if stop_event.is_set():
                    break
                time.sleep(0.1)

    finally:
        csvfile.close()


def main():
    pump = MZR7245Pump()

    stop_event = threading.Event()
    logger_thread = None
    running = False

    print("Pump controller ready.")
    print("Available commands: start, stop, exit")

    try:
        while True:
            command = input("> ").strip().lower()

            if command == "start":
                if running:
                    print("Pump is already running.")
                    continue

                print(f"Starting pump at {PUMP_SPEED} rpm...")
                pump.set_speed(PUMP_SPEED)

                stop_event.clear()
                logger_thread = threading.Thread(
                    target=logging_worker,
                    args=(pump, stop_event),
                    daemon=True,
                )
                logger_thread.start()

                running = True
                print("Pump started. Logging every 5 seconds.")

            elif command == "stop":
                if not running:
                    print("Pump is not running.")
                    continue

                print("Stopping pump...")
                stop_event.set()
                pump.stop()

                if logger_thread is not None:
                    logger_thread.join()

                running = False
                print("Pump stopped.")

            elif command == "exit":
                if running:
                    print("Stopping pump before exit...")
                    stop_event.set()
                    pump.stop()
                    if logger_thread is not None:
                        logger_thread.join()

                print("Exiting program.")
                break

            else:
                print("Unknown command. Use: start, stop, exit")

    finally:
        pump.close()


if __name__ == "__main__":
    main()