import serial
import serial.tools.list_ports
import threading
from datetime import datetime

# ==== Port Selection ====
ports = serial.tools.list_ports.comports()
ports_dict = {}

print("Available COM ports:")
for port in ports:
    portName = port.device  # e.g., 'COM4'
    com_num = portName.replace("COM", "")
    ports_dict[com_num] = portName
    print(f"{com_num}: {portName}")

com_input = input("Enter the COM port number (e.g., 4 for COM4): ").strip()
if com_input not in ports_dict:
    print("Invalid COM port number selected.")
    exit()

use = ports_dict[com_input]
print(f"Using port: {use}")


# ==== Serial Setup ====
serialInst = serial.Serial()
serialInst.baudrate = 9600
serialInst.port = use
serialInst.timeout = 1
serialInst.open()

# ==== Log File ====
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
log_file_path = f"arduino_log_{timestamp}.txt"
log_file = open(log_file_path, "a")

# ==== Background Reader ====
def read_from_arduino():
    while True:
        if serialInst.in_waiting:
            line = serialInst.readline().decode("utf-8", errors="ignore").strip()
            if line:
                log_file.write(line + "\n")
                log_file.flush()

# ==== Command Sender ====
def write_to_arduino():
    try:
        while True:
            command = input()
            if command.lower() == "exit":
                print("Exiting...")
                serialInst.close()
                log_file.close()
                break
            serialInst.write((command + "\n").encode("utf-8"))
    except KeyboardInterrupt:
        serialInst.close()
        log_file.close()

# ==== Start Threads ====
reader_thread = threading.Thread(target=read_from_arduino, daemon=True)
reader_thread.start()

write_to_arduino()  # Run on main thread
