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
const size_t COMMAND_BUFFER_SIZE = 64;

char commandBuffer[COMMAND_BUFFER_SIZE];
size_t commandLength = 0;
bool commandOverflowed = false;

void setup() {
  pinMode(SHUTTER_PIN, OUTPUT);
  digitalWrite(SHUTTER_PIN, LOW);

  Serial.begin(9600);
  Serial.println("READY shutter-v2");
}

void loop() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();

    if (c == '\r') {
      continue;
    }

    if (c == '\n') {
      commandBuffer[commandLength] = '\0';
      handleCommand(commandBuffer);
      commandLength = 0;
      commandOverflowed = false;
      continue;
    }

    if (commandLength >= COMMAND_BUFFER_SIZE - 1) {
      commandOverflowed = true;
      continue;
    }

    commandBuffer[commandLength] = c;
    commandLength++;
  }
}

void handleCommand(char *rawCommand) {
  if (commandOverflowed) {
    Serial.println("ERR command too long");
    return;
  }

  char *command = trimWhitespace(rawCommand);

  if (command[0] == '\0') {
    return;
  }

  char original[COMMAND_BUFFER_SIZE];
  copyText(original, command, COMMAND_BUFFER_SIZE);

  char *args = firstArg(command);

  if (equalsText(command, "ping")) {
    if (args == NULL || args[0] == '\0') {
      Serial.println("ERR missing ping id");
      return;
    }
    Serial.print("OK ping ");
    Serial.println(args);
    return;
  }

  if (equalsText(command, "shoot")) {
    if (args != NULL && args[0] != '\0') {
      handleShoot(args);
      return;
    }
    triggerShutter(DEFAULT_PULSE_MS);
    Serial.print("OK shoot ");
    Serial.print(DEFAULT_PULSE_MS);
    Serial.println(" ms");
    return;
  }

  if (equalsText(command, "press") || equalsText(command, "bulb_on")) {
    handlePress(args);
    return;
  }

  if (equalsText(command, "release") || equalsText(command, "bulb_off")) {
    handleRelease(args);
    return;
  }

  Serial.print("ERR unknown command ");
  Serial.println(original);
}

void handlePress(char *id) {
  digitalWrite(SHUTTER_PIN, HIGH);

  if (id != NULL && id[0] != '\0') {
    Serial.print("OK press ");
    Serial.println(id);
  } else {
    Serial.println("OK press");
  }
}

void handleRelease(char *id) {
  digitalWrite(SHUTTER_PIN, LOW);

  if (id != NULL && id[0] != '\0') {
    Serial.print("OK release ");
    Serial.println(id);
  } else {
    Serial.println("OK release");
  }
}

void handleShoot(char *args) {
  char *pulseText = trimWhitespace(args);
  char *id = firstArg(pulseText);

  unsigned long pulseMs = parseUnsignedLong(pulseText);
  if (pulseMs < MIN_PULSE_MS) {
    pulseMs = MIN_PULSE_MS;
  }

  if (id != NULL) {
    id = trimWhitespace(id);
  }

  triggerShutter(pulseMs);

  if (id != NULL && id[0] != '\0') {
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

bool equalsText(const char *left, const char *right) {
  return strcmp(left, right) == 0;
}

bool isWhitespace(char c) {
  return c == ' ' || c == '\t' || c == '\r' || c == '\n';
}

char *trimWhitespace(char *text) {
  while (isWhitespace(*text)) {
    text++;
  }

  char *end = text + strlen(text);
  while (end > text && isWhitespace(*(end - 1))) {
    end--;
  }
  *end = '\0';
  return text;
}

char *firstArg(char *text) {
  while (*text != '\0' && !isWhitespace(*text)) {
    text++;
  }

  if (*text == '\0') {
    return NULL;
  }

  *text = '\0';
  text++;
  return trimWhitespace(text);
}

unsigned long parseUnsignedLong(const char *text) {
  unsigned long value = 0;
  while (*text >= '0' && *text <= '9') {
    value = (value * 10) + (unsigned long)(*text - '0');
    text++;
  }
  return value;
}

void copyText(char *dest, const char *src, size_t destSize) {
  if (destSize == 0) {
    return;
  }

  size_t i = 0;
  while (i < destSize - 1 && src[i] != '\0') {
    dest[i] = src[i];
    i++;
  }
  dest[i] = '\0';
}