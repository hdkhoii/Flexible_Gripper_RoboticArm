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

const float MAX_SPEED_DEG_S = 80.0f;
const float ACCELERATION_DEG_S2 = 300.0f;
const unsigned long MOVE_INTERVAL_MS = 20;
const unsigned long STATUS_INTERVAL_MS = 100;
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

float moveToward(float current, float target, float maxChange)
{
  if (current < target)
  {
    return min(current + maxChange, target);
  }
  return max(current - maxChange, target);
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
        targetAngles[joint] = constrain(angle, 0.0f, 180.0f);
        targetActive[joint] = true;
      }
    }
    return;
  }

  if (command[0] == 'X' && command[1] == '\0')
  {
    // Dung ngay moi dich goc dang chay.
    for (uint8_t i = 0; i < JOINT_COUNT; ++i)
    {
      targetActive[i] = false;
      jointVelocities[i] = 0.0f;
    }
    printAngles();
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

  const unsigned long elapsedMs = now - lastMoveTime;
  if (elapsedMs < MOVE_INTERVAL_MS)
  {
    return;
  }

  lastMoveTime = now;
  const float deltaTime = min(elapsedMs, 100UL) / 1000.0f;
  const float maxSpeed = MAX_SPEED_DEG_S;
  const float maxVelocityChange = ACCELERATION_DEG_S2 * deltaTime;

  for (uint8_t i = 0; i < JOINT_COUNT; ++i)
  {
    const Joint joint = (Joint)i;
    float desiredVelocity = 0.0f;

    if (targetActive[i])
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

    if (targetActive[i])
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
  printAngles();
}

void loop()
{
  readSerialCommands();
  updateMotion();
}
