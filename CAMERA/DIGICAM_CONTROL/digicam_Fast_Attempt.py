import time
import requests

# === CONFIGURATION ===
number_of_photos = 20
capture_interval_seconds = 0.5
server_url = "http://localhost:5513/?CMD=Capture"

# === BAREBONE CAPTURE LOOP ===
for i in range(number_of_photos):
    requests.get(server_url)
    time.sleep(capture_interval_seconds)
