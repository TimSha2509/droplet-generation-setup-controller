import serial
import time


# =========================
# USER SETTINGS
# =========================

PORT = "COM4"

CHANNEL = 1  # 1 or 2
FREQUENCY_HZ = 10  # Frequency in Hz
AMPLITUDE_VPP = 5  # Amplitude in Vpp

ENABLE_OUTPUT = True  # True = output on, False = output off
SET_SINE_WAVE = True  # True = set waveform to sine first


# =========================
# PSG9080 CONTROL CLASS
# =========================


class PSG9080:
    def __init__(self, port="COM4", baudrate=115200, timeout=1):
        self.ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout,
        )
        time.sleep(0.2)

    def close(self):
        self.ser.close()

    def send(self, command):
        if not command.startswith(":"):
            command = ":" + command

        full_command = command + "\r\n"
        self.ser.write(full_command.encode("ascii"))

        time.sleep(0.05)
        response = self.ser.read_all().decode("ascii", errors="ignore").strip()

        print(f"Sent: {command}")
        if response:
            print(f"Response: {response}")

        return response

    def set_frequency_hz(self, channel, frequency_hz):
        scaled_frequency = int(round(frequency_hz * 1000))

        if channel == 1:
            return self.send(f":w13={scaled_frequency},0.")
        elif channel == 2:
            return self.send(f":w14={scaled_frequency},0.")
        else:
            raise ValueError("Channel must be 1 or 2.")

    def set_amplitude_vpp(self, channel, amplitude_vpp):
        scaled_amplitude = int(round(amplitude_vpp * 1000))

        if channel == 1:
            return self.send(f":w15={scaled_amplitude}.")
        elif channel == 2:
            return self.send(f":w16={scaled_amplitude}.")
        else:
            raise ValueError("Channel must be 1 or 2.")

    def enable_output(self, channel, enable=True):
        if channel == 1:
            ch1 = 1 if enable else 0
            ch2 = 0
        elif channel == 2:
            ch1 = 0
            ch2 = 1 if enable else 0
        else:
            raise ValueError("Channel must be 1 or 2.")

        return self.send(f":w10={ch1},{ch2}.")

    def set_sine_wave(self, channel):
        if channel == 1:
            return self.send(":w11=0.")
        elif channel == 2:
            return self.send(":w12=0.")
        else:
            raise ValueError("Channel must be 1 or 2.")


# =========================
# MAIN PROGRAM
# =========================

generator = PSG9080(port=PORT)

try:
    if SET_SINE_WAVE:
        generator.set_sine_wave(CHANNEL)

    generator.set_frequency_hz(CHANNEL, FREQUENCY_HZ)
    generator.set_amplitude_vpp(CHANNEL, AMPLITUDE_VPP)
    generator.enable_output(CHANNEL, ENABLE_OUTPUT)

    print("Done.")

finally:
    generator.close()
