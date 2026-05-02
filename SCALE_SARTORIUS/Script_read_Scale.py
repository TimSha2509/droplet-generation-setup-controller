import serial
import time

PORT = "COM3"

def try_read(baudrate=9600, parity=serial.PARITY_EVEN, stopbits=serial.STOPBITS_ONE, xonxoff=False, rtscts=False):
    ser = serial.Serial(
        port=PORT,
        baudrate=baudrate,
        bytesize=serial.SEVENBITS,
        parity=parity,
        stopbits=stopbits,
        timeout=1,
        xonxoff=xonxoff,
        rtscts=rtscts,
    )

    print(f"Opened {PORT} at {baudrate}, parity={parity}, stopbits={stopbits}, xonxoff={xonxoff}, rtscts={rtscts}")
    print("Reading for 10 seconds. Press PRINT on the balance or enable Autoprint.")
    start = time.time()

    try:
        while time.time() - start < 10:
            line = ser.readline()
            if line:
                print("RAW:", repr(line))
                try:
                    print("TXT:", line.decode("ascii", errors="replace").strip())
                except Exception as e:
                    print("Decode error:", e)
    finally:
        ser.close()

if __name__ == "__main__":
    try_read()