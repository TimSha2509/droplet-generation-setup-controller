import serial
import re
import csv
import time
from datetime import datetime

PORT = "COM3"
INTERVAL_SECONDS = 5
CSV_FILE = "scale_readings.csv"

ser = serial.Serial(
    port=PORT,
    baudrate=1200,
    bytesize=serial.SEVENBITS,
    parity=serial.PARITY_EVEN,
    stopbits=serial.STOPBITS_ONE,
    timeout=1,
    xonxoff=True,
)

pattern = re.compile(r"([+-]?\s*\d+\.\d+)\s*([a-zA-Z]+)")


def read_valid_weight(max_wait_seconds=4):
    start = time.time()

    while time.time() - start < max_wait_seconds:
        raw = ser.readline()

        if not raw:
            continue

        line = raw.decode("ascii", errors="replace").strip()

        if not line:
            continue

        match = pattern.search(line)

        if match:
            weight = float(match.group(1).replace(" ", ""))
            unit = match.group(2)
            return weight, unit, line

    return None, None, None


print(f"Reading newest valid scale value every {INTERVAL_SECONDS} seconds.")
print(f"Saving to: {CSV_FILE}")
print("Press Ctrl+C to stop.\n")

try:
    with open(CSV_FILE, mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)

        if file.tell() == 0:
            writer.writerow(["timestamp", "weight", "unit", "raw_text"])

        while True:
            ser.reset_input_buffer()

            weight, unit, line = read_valid_weight()

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if weight is not None:
                writer.writerow([timestamp, weight, unit, line])
                file.flush()
                print(f"{timestamp} | {weight} {unit}")
            else:
                print(f"{timestamp} | No valid weight received")

            time.sleep(INTERVAL_SECONDS)

except KeyboardInterrupt:
    print("\nStopped by user.")

finally:
    ser.close()
    print("Serial connection closed.")
