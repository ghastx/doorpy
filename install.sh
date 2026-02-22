#!/bin/bash
# ============================================================
# Script di installazione Sistema Citofono-VoIP
# Per Raspberry Pi 3B+ con citofono Terraneo
#
# Copyright (C) 2025 Simone
# License: GPL-2.0-or-later (vedi LICENSE)
# ============================================================

set -e

INSTALL_DIR="/opt/citofono-voip"
CONFIG_DIR="/etc/citofono-voip"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "============================================================"
echo "INSTALLAZIONE SISTEMA CITOFONO-VOIP"
echo "============================================================"

# Verifica root
if [ "$EUID" -ne 0 ]; then
    echo "Errore: eseguire come root (sudo ./install.sh)"
    exit 1
fi

# Installa dipendenze
echo ""
echo "[1/5] Installazione dipendenze..."
apt update
apt install -y \
    python3-rpi.gpio \
    baresip \
    baresip-core \
    alsa-utils

# Crea directory e copia file .py
echo ""
echo "[2/5] Installazione script in $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
for f in "$SCRIPT_DIR"/*.py; do
    [ -f "$f" ] && cp "$f" "$INSTALL_DIR/"
done
chmod +x "$INSTALL_DIR"/*.py

# Copia config.env.example in /etc/citofono-voip/config.env se non esiste
echo ""
echo "[3/5] Configurazione..."
mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG_DIR/config.env" ]; then
    cp "$SCRIPT_DIR/config.env.example" "$CONFIG_DIR/config.env"
    chmod 600 "$CONFIG_DIR/config.env"
    echo "File di configurazione creato: $CONFIG_DIR/config.env"
    echo "  >>> ATTENZIONE: modifica la password SIP prima di avviare! <<<"
else
    echo "File di configurazione esistente preservato: $CONFIG_DIR/config.env"
fi

# Crea servizio systemd
echo ""
echo "[4/5] Creazione servizio systemd..."
cp "$SCRIPT_DIR/citofono-voip.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable citofono-voip

# Crea directory log
mkdir -p /var/log
touch /var/log/citofono-voip.log
chmod 644 /var/log/citofono-voip.log

# Riepilogo
echo ""
echo "[5/5] Verifica installazione..."
echo "  Script principale: $INSTALL_DIR/citofono-voip.py"
echo "  Configurazione:    $CONFIG_DIR/config.env"
echo "  Servizio systemd:  /etc/systemd/system/citofono-voip.service"
echo "  Log:               /var/log/citofono-voip.log"

echo ""
echo "============================================================"
echo "INSTALLAZIONE COMPLETATA!"
echo "============================================================"
echo ""
echo "Prossimi passi:"
echo ""
echo "1. MODIFICA LA CONFIGURAZIONE:"
echo "   sudo nano $CONFIG_DIR/config.env"
echo "   Imposta almeno: SIP_PASSWORD, SIP_DOMAIN, NUMERO_DA_CHIAMARE"
echo ""
echo "2. CONFIGURA IL GRANDSTREAM:"
echo "   - Crea un interno per il citofono (es. 2000)"
echo "   - Crea un Ring Group per far squillare gli interni desiderati"
echo ""
echo "3. TESTA I COMPONENTI:"
echo "   sudo $INSTALL_DIR/test_audio.sh                  # Test audio"
echo "   sudo python3 $INSTALL_DIR/test_suoneria.py       # Test suoneria"
echo "   sudo python3 $INSTALL_DIR/test_portone.py        # Test relè"
echo ""
echo "4. AVVIA IL SERVIZIO:"
echo "   sudo systemctl start citofono-voip"
echo "   sudo journalctl -u citofono-voip -f              # Vedi log"
echo ""
echo "5. VERIFICA REGISTRAZIONE SIP:"
echo "   Controlla sul Grandstream che l'interno sia registrato"
echo ""
