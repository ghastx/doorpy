#!/bin/bash
# Test audio per Citofono VoIP
#
# Copyright (C) 2025 Simone
# License: GPL-2.0-or-later (vedi LICENSE)

echo "=== Test Audio Citofono VoIP ==="
echo ""
echo "Dispositivi di riproduzione:"
aplay -l
echo ""
echo "Dispositivi di registrazione:"
arecord -l
echo ""
echo "--- Test registrazione (5 secondi) ---"
echo "Parla nel microfono..."
arecord -D hw:1,0 -f cd -d 5 /tmp/test_audio.wav
echo ""
echo "--- Test riproduzione ---"
aplay -D hw:1,0 /tmp/test_audio.wav
echo ""
echo "Regola i volumi con: alsamixer -c 1"
