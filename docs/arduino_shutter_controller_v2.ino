/*
  Nikon Z6 shutter trigger via PC817 optocoupler module

  Wiring:
  Arduino D8  -> module IN+
  Arduino GND -> module IN-

  Module OUT  -> Nikon red + yellow wires
  Module GND  -> Nikon white wire
  Module VCC  -> not connected

  Protocol v2:
  On startup:
    READY shutter-v2

  Commands:
    ping <id>         -> OK ping <id>
    press <id>        -> OK press <id>
    release <id>      -> OK release <id>
    shoot <ms> <id>   -> OK shoot <id> <ms> ms

  Legacy/manual commands are kept:
    shoot
    shoot <ms>
    press
    release
    bulb_on
    bulb_off
*/

const int SHUTTER_PIN = 8;

const unsigned long DEFAULT_PULSE_MS = 300;
const unsigned long MIN_PULSE_MS = 50;
const unsigned long SERIAL_READ_TIMEOUT_MS = 100;

void setup() {
  pinMode(SHUTTER_PIN, OUTPUT);
  digitalWrite(SHUTTER_PIN, LOW);

  Serial.begin(9600);
  Serial.setTimeout(SERIAL_READ_TIMEOUT_MS);
  Serial.println("READY shutter-v2");
}

void loop() {
  if (Serial.available() <= 0) {
    return;
  }

  String command = Serial.readStringUntil('\n');
  command.trim();

  if (command.length() == 0) {
    return;
  }

  if (command.startsWith("ping ")) {
    String id = command.substring(5);
    id.trim();
    Serial.print("OK ping ");
    Serial.println(id);
    return;
  }

  if (command == "shoot") {
    triggerShutter(DEFAULT_PULSE_MS);
    Serial.print("OK shoot ");
    Serial.print(DEFAULT_PULSE_MS);
    Serial.println(" ms");
    return;
  }

  if (command.startsWith("shoot ")) {
    handleShoot(command.substring(6));
    return;
  }

  if (command == "press" || command == "bulb_on" || command.startsWith("press ")) {
    handlePress(command);
    return;
  }

  if (command == "release" || command == "bulb_off" || command.startsWith("release ")) {
    handleRelease(command);
    return;
  }

  Serial.print("ERR unknown command ");
  Serial.println(command);
}

void handlePress(String command) {
  digitalWrite(SHUTTER_PIN, HIGH);

  String id = "";
  if (command.startsWith("press ")) {
    id = command.substring(6);
    id.trim();
  }

  if (id.length() > 0) {
    Serial.print("OK press ");
    Serial.println(id);
  } else {
    Serial.println("OK press");
  }
}

void handleRelease(String command) {
  digitalWrite(SHUTTER_PIN, LOW);

  String id = "";
  if (command.startsWith("release ")) {
    id = command.substring(8);
    id.trim();
  }

  if (id.length() > 0) {
    Serial.print("OK release ");
    Serial.println(id);
  } else {
    Serial.println("OK release");
  }
}

void handleShoot(String args) {
  args.trim();

  int separator = args.indexOf(' ');
  String pulseText = args;
  String id = "";

  if (separator >= 0) {
    pulseText = args.substring(0, separator);
    id = args.substring(separator + 1);
    id.trim();
  }

  unsigned long pulseMs = pulseText.toInt();
  if (pulseMs < MIN_PULSE_MS) {
    pulseMs = MIN_PULSE_MS;
  }

  triggerShutter(pulseMs);

  if (id.length() > 0) {
    Serial.print("OK shoot ");
    Serial.print(id);
    Serial.print(" ");
    Serial.print(pulseMs);
    Serial.println(" ms");
  } else {
    Serial.print("OK shoot ");
    Serial.print(pulseMs);
    Serial.println(" ms");
  }
}

void triggerShutter(unsigned long pulseMs) {
  digitalWrite(SHUTTER_PIN, HIGH);
  delay(pulseMs);
  digitalWrite(SHUTTER_PIN, LOW);
}
