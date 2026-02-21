#!/usr/bin/env python3
"""
Test apertura portone.

Copyright (C) 2025 Simone
License: GPL-2.0-or-later (vedi LICENSE)
"""
import RPi.GPIO as GPIO
import time
import sys

PIN_RELE = 27
DURATA = int(sys.argv[1]) if len(sys.argv) > 1 else 2

GPIO.setmode(GPIO.BCM)
GPIO.setup(PIN_RELE, GPIO.OUT)

print(f"Attivazione relè GPIO{PIN_RELE} per {DURATA}s...")
GPIO.output(PIN_RELE, GPIO.HIGH)
time.sleep(DURATA)
GPIO.output(PIN_RELE, GPIO.LOW)
print("Fatto!")

GPIO.cleanup()
