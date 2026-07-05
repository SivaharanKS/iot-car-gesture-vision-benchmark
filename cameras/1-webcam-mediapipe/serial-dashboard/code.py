import robot
import pid_controller
import asyncio
import time
import supervisor
import sys
import json
import math

# Vitesse d'avance (fraction du duty cycle max, entre 0 et 1)
FORWARD_SPEED = 0.25

# Vitesse de rotation en pivot (tant que le geste de virage est detecte)
TURN_SPEED = 0.3

# Etat partage du mode de deplacement courant
state = {"mode": "stop"}  # "stop" | "forward" | "turn_left" | "turn_right"

# Delai maximum (en secondes) sans commande recue avant arret de securite
COMMAND_TIMEOUT = 0.4
last_command_time = time.monotonic()

# Position estimee du robot (odometrie), en metres, dans le repere de depart
pos_x = 0.0
pos_y = 0.0
last_left_ticks = robot.left_encoder.read()
last_right_ticks = robot.right_encoder.read()


async def update_odometry(dt, angle_deg):
    """Met a jour la position (pos_x, pos_y) a partir des encodeurs et de l'angle IMU."""
    global pos_x, pos_y, last_left_ticks, last_right_ticks

    left_ticks = robot.left_encoder.read()
    right_ticks = robot.right_encoder.read()

    delta_left = (left_ticks - last_left_ticks) * robot.ticks_to_m
    delta_right = (right_ticks - last_right_ticks) * robot.ticks_to_m

    last_left_ticks = left_ticks
    last_right_ticks = right_ticks

    distance = (delta_left + delta_right) / 2
    angle_rad = math.radians(angle_deg)

    pos_x += distance * math.cos(angle_rad)
    pos_y += distance * math.sin(angle_rad)


async def command_handler():
    global last_command_time

    while True:
        if supervisor.runtime.serial_bytes_available:
            line = sys.stdin.readline().strip()

            try:
                data = json.loads(line)
            except Exception:
                await asyncio.sleep(0)
                continue

            cmd = data.get("cmd", "")
            last_command_time = time.monotonic()

            if cmd == "forward":
                state["mode"] = "forward"

            elif cmd == "stop":
                state["mode"] = "stop"
                robot.stop()

            elif cmd == "turn_left":
                state["mode"] = "turn_left"

            elif cmd == "turn_right":
                state["mode"] = "turn_right"

        await asyncio.sleep(0)


async def calibrate_gyro_bias(num_samples=100, delay=0.005):
    """Mesure le biais du gyroscope au repos (robot immobile) au demarrage,
    pour le soustraire ensuite et reduire la derive de l'angle."""
    total = 0.0
    for _ in range(num_samples):
        total += robot.imu.gyro[2]
        await asyncio.sleep(delay)
    return total / num_samples


async def angel_caculate(dt, radps, bias):
    angel = robot.last_angel + float((radps - bias) / 3.14 * 180 * dt)
    robot.last_angel = angel
    return angel


async def control_loop():
    asyncio.create_task(command_handler())

    robot.send_line("Calibration du gyroscope, ne pas bouger le robot...")
    gyro_bias = await calibrate_gyro_bias()
    robot.send_line(f"Calibration terminee, biais={gyro_bias:.5f}")

    last_time = time.monotonic()

    while True:
        await asyncio.sleep(0.1)
        next_time = time.monotonic()
        dt = next_time - last_time
        last_time = next_time

        angle = await angel_caculate(dt, robot.imu.gyro[2], gyro_bias)
        await update_odometry(dt, angle)

        # Securite : si aucune commande n'est recue depuis trop longtemps,
        # on force l'arret du robot (main hors du cadre, webcam coupee, etc.)
        if time.monotonic() - last_command_time > COMMAND_TIMEOUT:
            state["mode"] = "stop"

        if state["mode"] == "forward":
            robot.set_all(FORWARD_SPEED)
        elif state["mode"] == "turn_left":
            robot.set_left(-TURN_SPEED)
            robot.set_right(TURN_SPEED)
        elif state["mode"] == "turn_right":
            robot.set_left(TURN_SPEED)
            robot.set_right(-TURN_SPEED)
        elif state["mode"] == "stop":
            robot.stop()

        robot.send_line(
            f"x={pos_x:.3f} y={pos_y:.3f} angle={angle:.1f} mode={state['mode']}"
        )


async def main():
    await asyncio.sleep(0.5)
    robot.send_line("Ready to go!")
    await control_loop()


asyncio.run(main())