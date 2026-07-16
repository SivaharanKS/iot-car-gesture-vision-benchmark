import board
import pwmio
import digitalio
import pio_encoder
import adafruit_hcsr04
import busio
import math
import adafruit_mpu6050

wheel_diameter_mm = 65
wheel_circumference_mm = math.pi * wheel_diameter_mm
gear_ratio = 90
encoder_poles = 52
ticks_per_revolution = encoder_poles * gear_ratio
ticks_to_m = (wheel_circumference_mm / ticks_per_revolution) / 1000
m_to_ticks = 1 / ticks_to_m
last_angel = 0.0

motor_A1 = digitalio.DigitalInOut(board.GP18)
motor_A2 = digitalio.DigitalInOut(board.GP17)
motor_B1 = digitalio.DigitalInOut(board.GP20)
motor_B2 = digitalio.DigitalInOut(board.GP21)
motor_stby = digitalio.DigitalInOut(board.GP19)

motor_A1.direction = digitalio.Direction.OUTPUT
motor_A2.direction = digitalio.Direction.OUTPUT
motor_B1.direction = digitalio.Direction.OUTPUT
motor_B2.direction = digitalio.Direction.OUTPUT
motor_stby.direction = digitalio.Direction.OUTPUT
motor_stby.value = True

motor_Val_A = pwmio.PWMOut(board.GP16)
motor_Val_B = pwmio.PWMOut(board.GP22)

left_motor = motor_A1, motor_A2
right_motor = motor_B1, motor_B2
max_speed = 2 ** 16 - 1

left_encoder = pio_encoder.QuadratureEncoder(board.GP26, board.GP27)
right_encoder = pio_encoder.QuadratureEncoder(board.GP28, board.GP29, reversed=True)

front_distance = adafruit_hcsr04.HCSR04(trigger_pin=board.GP4, echo_pin=board.GP5)

i2c0 = busio.I2C(sda=board.GP6, scl=board.GP7)

imu = adafruit_mpu6050.MPU6050(i2c0)

def stop():
	motor_A1.value = False
	motor_A2.value = False
	motor_B1.value = False
	motor_B2.value = False
	motor_Val_A.duty_cycle = motor_Val_B.duty_cycle = 0


def set_speed(motor, speed):
	# Swap motor pins if we reverse the speed
	if speed < 0:
		motor[0].value = False
		motor[1].value = True
		speed = -speed
	elif speed == 0:
		stop()
	elif speed > 0:
		motor[0].value = True
		motor[1].value = False
		speed = min(speed, 1)  # limit to 1.0
	if motor == left_motor:
		motor_Val_A.duty_cycle = int(max_speed * speed)
	else:
		motor_Val_B.duty_cycle = int(max_speed * speed)


def set_left(speed):
	set_speed(left_motor, speed)

def set_right(speed):
	set_speed(right_motor, speed)

def set_all(speed):
	set_speed(left_motor, speed)
	set_speed(right_motor, speed)

def send_line(message):
	print(f"{message}".encode())