# Edge Impulse - OpenMV Image Classification Example
#
# This work is licensed under the MIT license.
# Copyright (c) 2013-2024 OpenMV LLC. All rights reserved.
# https://github.com/openmv/openmv/blob/master/LICENSE

import sensor
import time
import ml

sensor.reset()  # Reset and initialize the sensor.
sensor.set_pixformat(sensor.RGB565)  # Set pixel format to RGB565 (or GRAYSCALE)
sensor.set_framesize(sensor.QVGA)  # Set frame size to QVGA (320x240)
sensor.set_windowing((240, 240))  # Set 240x240 window.
sensor.skip_frames(time=2000)  # Let the camera adjust.

model = ml.Model("trained")#mobilenet, load_to_fb=True)

clock = time.clock()
while True:
    clock.tick()

    img = sensor.snapshot()

    print("**********\nPredictions for each class")
    # This combines the labels and confidence values into a list of tuples
    # and then sorts that list by the confidence values.
    sorted_list = sorted(
        zip(model.labels, model.predict([img])[0].flatten().tolist()), key=lambda x: x[1], reverse=True
    )
    for i in range(len(sorted_list)):
        print("%s = %f" % (sorted_list[i][0], sorted_list[i][1]))
    print(clock.fps(), "fps")
