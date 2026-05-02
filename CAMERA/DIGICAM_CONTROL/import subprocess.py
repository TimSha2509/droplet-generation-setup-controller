import subprocess
import time
from datetime import datetime
import threading
import keyboard
import os

# === SHARED ABORT FLAG ===
abort_flag = {'abort': False}

# === CONFIGURATION ===
exe_path = r"C:\Program Files (x86)\digiCamControl\CameraControlCmd.exe"
capture_interval_seconds = 0.5
number_of_photos = 20
abort_key = 'esc'
camera_settings = {
    'iso': '400',
    'shutterspeed': '1/100',
    'aperture': '5.6'
}
save_directory = r'C:\Users\mtimshar\Pictures\digiCamControl\Session1'

# === MAKE SURE DIRECTORY EXISTS ===
os.makedirs(save_directory, exist_ok=True)

# === ABORT LISTENER ===
def listen_for_abort():
    print(f"[INFO] Press '{abort_key.upper()}' at any time to abort.")
    keyboard.wait(abort_key)
    abort_flag['abort'] = True
    print(f"\n[ABORT] '{abort_key.upper()}' pressed. Aborting...")

# Start abort listener thread
threading.Thread(target=listen_for_abort, daemon=True).start()

# === SET CAMERA PARAMETERS ===
print("[INFO] Setting camera parameters...")
for key, value in camera_settings.items():
    subprocess.run([exe_path, '/set', f'{key}={value}'])

print("[INFO] Starting photo capture...\n")

# === PHOTO LOOP ===
for i in range(number_of_photos):
    if abort_flag['abort']:
        print(f"[ABORTED] Before photo {i + 1}.")
        break

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]  # e.g., 20250612_190101_123
    filename = os.path.join(save_directory, f'photo_{timestamp}.jpg')

    print(f"[{i + 1}/{number_of_photos}] Capturing: {filename}")
    subprocess.run([exe_path, '/capture', '/filename', filename])

    if i < number_of_photos - 1:
        # Wait for interval, but check for abort every 0.05 seconds
        sleep_time = 0
        while sleep_time < capture_interval_seconds:
            if abort_flag['abort']:
                print(f"[ABORTED] During wait after photo {i + 1}.")
                exit(0)
            time.sleep(0.05)
            sleep_time += 0.05

print("\n[INFO] Capture session complete.")
