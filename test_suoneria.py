#!/usr/bin/env python3
"""
Test rilevamento suoneria.

Copyright (C) 2025 Simone
License: GPL-2.0-or-later (vedi LICENSE)
"""
import RPi.GPIO as GPIO
import time

PIN_SUONERIA = 17

GPIO.setmode(GPIO.BCM)
GPIO.setup(PIN_SUONERIA, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

print(f"Monitoraggio GPIO{PIN_SUONERIA} - Premi Ctrl+C per uscire")
print("Fai suonare il citofono...")

try:
    while True:
        stato = GPIO.input(PIN_SUONERIA)
        if stato:
            print(f"[{time.strftime('%H:%M:%S')}] SUONERIA RILEVATA!")
        time.sleep(0.1)
except KeyboardInterrupt:
    print("\nUscita")
finally:
    GPIO.cleanup()
