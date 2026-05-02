import time
import threading
import keyboard
import requests

# === ABORT FLAG ===
abort_flag = {'abort': False}

# === CONFIGURATION ===
capture_interval_seconds = 5
number_of_photos = 3
abort_key = 'esc'
server_url = "http://localhost:5513/?CMD=Capture"

# === ABORT LISTENER ===
def listen_for_abort():
    print(f"[INFO] Press '{abort_key.upper()}' at any time to abort.")
    keyboard.wait(abort_key)
    abort_flag['abort'] = True
    print(f"\n[ABORT] '{abort_key.upper()}' pressed. Aborting...")

threading.Thread(target=listen_for_abort, daemon=True).start()

print("[INFO] Starting fast capture using HTTP...\n")

# === CAPTURE LOOP ===
for i in range(number_of_photos):
    if abort_flag['abort']:
        print(f"[ABORTED] Before photo {i + 1}.")
        break

    print(f"[{i + 1}/{number_of_photos}] Capturing...")
    try:
        requests.get(server_url)
    except Exception as e:
        print(f"[ERROR] Capture failed: {e}")
        break

    if i < number_of_photos - 1:
        sleep_time = 0
        while sleep_time < capture_interval_seconds:
            if abort_flag['abort']:
                print(f"[ABORTED] During wait after photo {i + 1}.")
                exit(0)
            time.sleep(0.05)
            sleep_time += 0.05

print("\n[INFO] Capture session complete.")
