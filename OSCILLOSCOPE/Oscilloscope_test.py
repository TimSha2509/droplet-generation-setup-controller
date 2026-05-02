import csv
from datetime import datetime
import pyvisa

RESOURCE = "USB0::0x2A8D::0x1778::MY55440264::0::INSTR"
CSV_FILE = "experiment_log.csv"

def ask_optional_float(prompt):
    text = input(prompt).strip()
    if text == "":
        return ""
    try:
        return float(text)
    except ValueError:
        print("Invalid number, leaving blank.")
        return ""

rm = pyvisa.ResourceManager()
scope = rm.open_resource(RESOURCE)

scope.timeout = 5000
scope.write_termination = "\n"
scope.read_termination = "\n"

print("Connected to:", scope.query("*IDN?").strip())

try:
    with open(CSV_FILE, "x", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp",
            "set_freq_nominal_hz",
            "set_amp_nominal",
            "ch1_freq_hz",
            "ch1_vpp_v",
            "ch2_vrms_dc_v",
            "ch3_vrms_dc_v",
            "comment"
        ])
except FileExistsError:
    pass

print("\nPress Enter to capture one data point, or type q to quit.\n")

try:
    while True:
        cmd = input("Capture [Enter] / Quit [q]: ").strip().lower()
        if cmd == "q":
            break

        set_freq_nominal = ask_optional_float("Nominal generator frequency [Hz] (optional): ")
        set_amp_nominal = ask_optional_float("Nominal amplifier setting (optional): ")
        comment = input("Comment (optional): ").strip()

        ch1_freq = float(scope.query(":MEASure:FREQuency? CHAN1"))
        ch1_vpp = float(scope.query(":MEASure:VPP? CHAN1"))
        ch2_vrms_dc = float(scope.query(":MEASure:VRMS? DISPlay,DC,CHAN2"))
        ch3_vrms_dc = float(scope.query(":MEASure:VRMS? DISPlay,DC,CHAN3"))

        timestamp = datetime.now().isoformat(timespec="seconds")

        with open(CSV_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                timestamp,
                set_freq_nominal,
                set_amp_nominal,
                ch1_freq,
                ch1_vpp,
                ch2_vrms_dc,
                ch3_vrms_dc,
                comment
            ])

        print("Saved:")
        print(f"  CH1 frequency    = {ch1_freq:.6g} Hz")
        print(f"  CH1 Vpp          = {ch1_vpp:.6g} V")
        print(f"  CH2 VRMS DC      = {ch2_vrms_dc:.6g} V")
        print(f"  CH3 VRMS DC      = {ch3_vrms_dc:.6g} V")
        print()

finally:
    scope.close()
    rm.close()