#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>
#include <math.h>

#define MIN_PULSE_WIDTH 650
#define MAX_PULSE_WIDTH 2350
#define FREQUENCY 50

Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver();

enum Joint : uint8_t
{
  HAND,
  WRIST,
  ELBOW,
  SHOULDER,
  BASE,
  JOINT_COUNT
};

const uint8_t SERVO_CHANNELS[JOINT_COUNT] = {11, 12, 10, 14, 15};

// Giu goc va van toc o dang so thuc de khong bi nhay theo tung bac 1..4 do.
float jointAngles[JOINT_COUNT] = {150.0f, 90.0f, 180.0f, 0.0f, 90.0f};
float jointVelocities[JOINT_COUNT] = {0.0f, 0.0f, 0.0f, 0.0f, 0.0f};
float targetAngles[JOINT_COUNT] = {150.0f, 90.0f, 180.0f, 0.0f, 90.0f};
bool targetActive[JOINT_COUNT] = {false, false, false, false, false};
uint16_t lastPwmTicks[JOINT_COUNT] = {0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF};

const float SPEED_LEVELS[] = {25.0f, 50.0f, 80.0f, 120.0f};
uint8_t speedLevel = 3;
const float ACCELERATION_DEG_S2 = 300.0f;
const unsigned long MOVE_INTERVAL_MS = 20;
const unsigned long COMMAND_TIMEOUT_MS = 250;
const unsigned long STATUS_INTERVAL_MS = 100;

enum KeyMask : uint16_t
{
  KEY_Q = 1 << 0,
  KEY_A = 1 << 1,
  KEY_W = 1 << 2,
  KEY_S = 1 << 3,
  KEY_E = 1 << 4,
  KEY_D = 1 << 5,
  KEY_R = 1 << 6,
  KEY_F = 1 << 7,
  KEY_T = 1 << 8,
  KEY_G = 1 << 9
};

uint16_t heldKeys = 0;
unsigned long lastCommandTime = 0;
unsigned long lastMoveTime = 0;
unsigned long lastStatusTime = 0;

char commandBuffer[20];
uint8_t commandLength = 0;

uint16_t angleToPulse(float angle)
{
  angle = constrain(angle, 0.0f, 180.0f);
  const float pulseWidth = MIN_PULSE_WIDTH
                         + angle * (MAX_PULSE_WIDTH - MIN_PULSE_WIDTH) / 180.0f;
  return (uint16_t)(pulseWidth * FREQUENCY * 4096.0f / 1000000.0f + 0.5f);
}

void updateServo(Joint joint)
{
  const uint16_t ticks = angleToPulse(jointAngles[joint]);
  if (ticks == lastPwmTicks[joint])
  {
    return;
  }

  pwm.setPWM(SERVO_CHANNELS[joint], 0, ticks);
  lastPwmTicks[joint] = ticks;
}

void updateAllServos()
{
  for (uint8_t i = 0; i < JOINT_COUNT; ++i)
  {
    updateServo((Joint)i);
  }
}

void printAngles()
{
  Serial.print("A,");
  for (uint8_t i = 0; i < JOINT_COUNT; ++i)
  {
    Serial.print((int)(jointAngles[i] + 0.5f));
    if (i + 1 < JOINT_COUNT)
    {
      Serial.print(',');
    }
  }
  Serial.println();
}

void printSpeed()
{
  Serial.print("V,");
  Serial.println(speedLevel);
}

uint16_t maskForKey(char key)
{
  switch (key)
  {
    case 'q': return KEY_Q;
    case 'a': return KEY_A;
    case 'w': return KEY_W;
    case 's': return KEY_S;
    case 'e': return KEY_E;
    case 'd': return KEY_D;
    case 'r': return KEY_R;
    case 'f': return KEY_F;
    case 't': return KEY_T;
    case 'g': return KEY_G;
    default: return 0;
  }
}

int8_t directionForJoint(Joint joint, uint16_t keys)
{
  switch (joint)
  {
    case HAND: return ((keys & KEY_A) != 0) - ((keys & KEY_Q) != 0);
    case WRIST: return ((keys & KEY_S) != 0) - ((keys & KEY_W) != 0);
    case ELBOW: return ((keys & KEY_D) != 0) - ((keys & KEY_E) != 0);
    case SHOULDER: return ((keys & KEY_F) != 0) - ((keys & KEY_R) != 0);
    case BASE: return ((keys & KEY_G) != 0) - ((keys & KEY_T) != 0);
    default: return 0;
  }
}

float moveToward(float current, float target, float maxChange)
{
  if (current < target)
  {
    return min(current + maxChange, target);
  }
  return max(current - maxChange, target);
}

void setPreset(float angle)
{
  heldKeys = 0;
  for (uint8_t i = 0; i < JOINT_COUNT; ++i)
  {
    targetAngles[i] = constrain(angle, 0.0f, 180.0f);
    targetActive[i] = true;
  }
}

void processCommand(const char *command)
{
  // G<joint>,<angle>  — dat goc truc tiep cho mot khop (tu slider GUI)
  if (command[0] == 'G')
  {
    const char *comma = strchr(command + 1, ',');
    if (comma != nullptr)
    {
      const uint8_t joint = (uint8_t)atoi(command + 1);
      const float angle   = (float)atof(comma + 1);
      if (joint < JOINT_COUNT)
      {
        heldKeys &= ~(1u << (joint * 2)) & ~(1u << (joint * 2 + 1)); // giai phong phim khop do
        targetAngles[joint] = constrain(angle, 0.0f, 180.0f);
        targetActive[joint] = true;
        lastCommandTime = millis();
      }
    }
    return;
  }

  if (command[0] == 'K')
  {
    uint16_t newHeldKeys = 0;
    for (uint8_t i = 1; command[i] != '\0'; ++i)
    {
      newHeldKeys |= maskForKey(command[i]);
    }

    for (uint8_t i = 0; i < JOINT_COUNT; ++i)
    {
      if (directionForJoint((Joint)i, newHeldKeys) != 0)
      {
        targetActive[i] = false;
      }
    }

    heldKeys = newHeldKeys;
    lastCommandTime = millis();
    return;
  }

  if (command[0] == '0' && command[1] == '\0')
  {
    setPreset(0.0f);
  }
  else if (command[0] == '9' && command[1] == '\0')
  {
    setPreset(90.0f);
  }
  else if (command[0] == 'H' && command[1] == '\0')
  {
    heldKeys &= ~(KEY_Q | KEY_A);
    targetAngles[HAND] = 0.0f;
    targetActive[HAND] = true;
  }
  else if (command[0] == 'V' && command[1] >= '1' && command[1] <= '4' && command[2] == '\0')
  {
    const uint8_t newLevel = command[1] - '0';
    if (newLevel != speedLevel)
    {
      speedLevel = newLevel;
      printSpeed();
    }
  }
}

void readSerialCommands()
{
  while (Serial.available() > 0)
  {
    const char incoming = Serial.read();

    if (incoming == '\n' || incoming == '\r')
    {
      if (commandLength > 0)
      {
        commandBuffer[commandLength] = '\0';
        processCommand(commandBuffer);
        commandLength = 0;
      }
    }
    else if (commandLength < sizeof(commandBuffer) - 1)
    {
      commandBuffer[commandLength++] = incoming;
    }
    else
    {
      commandLength = 0;
    }
  }
}

void updateMotion()
{
  const unsigned long now = millis();

  if (heldKeys != 0 && now - lastCommandTime > COMMAND_TIMEOUT_MS)
  {
    heldKeys = 0;
  }

  const unsigned long elapsedMs = now - lastMoveTime;
  if (elapsedMs < MOVE_INTERVAL_MS)
  {
    return;
  }

  lastMoveTime = now;
  const float deltaTime = min(elapsedMs, 100UL) / 1000.0f;
  const float maxSpeed = SPEED_LEVELS[speedLevel - 1];
  const float maxVelocityChange = ACCELERATION_DEG_S2 * deltaTime;

  for (uint8_t i = 0; i < JOINT_COUNT; ++i)
  {
    const Joint joint = (Joint)i;
    const int8_t direction = directionForJoint(joint, heldKeys);
    float desiredVelocity = direction * maxSpeed;

    if (direction == 0 && targetActive[i])
    {
      const float distance = targetAngles[i] - jointAngles[i];
      if (fabsf(distance) < 0.05f && fabsf(jointVelocities[i]) <= maxVelocityChange)
      {
        jointAngles[i] = targetAngles[i];
        jointVelocities[i] = 0.0f;
        targetActive[i] = false;
        updateServo(joint);
        continue;
      }

      // Gioi han van toc theo khoang cach phanh: v = sqrt(2 * a * s).
      const float brakingSpeed = sqrtf(2.0f * ACCELERATION_DEG_S2 * fabsf(distance));
      desiredVelocity = (distance < 0.0f ? -1.0f : 1.0f) * min(maxSpeed, brakingSpeed);
    }

    jointVelocities[i] = moveToward(
      jointVelocities[i], desiredVelocity, maxVelocityChange
    );

    const float previousDistance = targetAngles[i] - jointAngles[i];
    jointAngles[i] += jointVelocities[i] * deltaTime;

    if (direction == 0 && targetActive[i])
    {
      const float newDistance = targetAngles[i] - jointAngles[i];
      if ((previousDistance > 0.0f && newDistance <= 0.0f)
          || (previousDistance < 0.0f && newDistance >= 0.0f))
      {
        jointAngles[i] = targetAngles[i];
        jointVelocities[i] = 0.0f;
        targetActive[i] = false;
      }
    }

    if (jointAngles[i] <= 0.0f)
    {
      jointAngles[i] = 0.0f;
      jointVelocities[i] = max(0.0f, jointVelocities[i]);
    }
    else if (jointAngles[i] >= 180.0f)
    {
      jointAngles[i] = 180.0f;
      jointVelocities[i] = min(0.0f, jointVelocities[i]);
    }

    updateServo(joint);
  }

  if (now - lastStatusTime >= STATUS_INTERVAL_MS)
  {
    lastStatusTime = now;
    printAngles();
  }
}

void setup()
{
  Serial.begin(115200);
  pwm.begin();
  pwm.setPWMFreq(FREQUENCY);
  delay(500);

  lastMoveTime = millis();
  updateAllServos();
  Serial.println("READY");
  printSpeed();
  printAngles();
}

void loop()
{
  readSerialCommands();
  updateMotion();
}
