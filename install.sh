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
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "============================================================"
echo "INSTALLAZIONE SISTEMA CITOFONO-VOIP"
echo "============================================================"

# Verifica root
if [ "$EUID" -ne 0 ]; then
    echo "Errore: eseguire come root (sudo ./install.sh)"
    exit 1
fi

# Update sistema
echo ""
echo "[1/6] Aggiornamento sistema..."
apt update
apt upgrade -y

# Installa dipendenze
echo ""
echo "[2/6] Installazione dipendenze..."
apt install -y \
    baresip \
    baresip-core \
    python3-rpi.gpio \
    python3-pip \
    alsa-utils \
    libasound2-dev

# Configura audio
echo ""
echo "[3/6] Configurazione audio..."
cat > /etc/asound.conf << 'EOF'
# Configurazione ALSA per Citofono VoIP
# Scheda USB come default

pcm.!default {
    type hw
    card 1
    device 0
}

ctl.!default {
    type hw
    card 1
}

# Dispositivo per cattura
pcm.mic {
    type hw
    card 1
    device 0
}

# Dispositivo per riproduzione
pcm.speaker {
    type hw
    card 1
    device 0
}
EOF
echo "Configurazione ALSA creata."

# Crea directory e copia script
echo ""
echo "[4/6] Installazione script..."
mkdir -p "$INSTALL_DIR"
cp "$SCRIPT_DIR/citofono-voip.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/test_portone.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/test_suoneria.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/test_audio.sh" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/citofono-voip.py"
chmod +x "$INSTALL_DIR/test_portone.py"
chmod +x "$INSTALL_DIR/test_suoneria.py"
chmod +x "$INSTALL_DIR/test_audio.sh"

# Crea config.env da esempio se non esiste già
if [ ! -f "$INSTALL_DIR/config.env" ]; then
    cp "$SCRIPT_DIR/config.env.example" "$INSTALL_DIR/config.env"
    chmod 600 "$INSTALL_DIR/config.env"
    echo "File di configurazione creato: $INSTALL_DIR/config.env"
    echo "  >>> ATTENZIONE: modifica la password SIP prima di avviare! <<<"
else
    echo "File di configurazione esistente preservato: $INSTALL_DIR/config.env"
fi

# Crea servizio systemd
echo ""
echo "[5/6] Creazione servizio systemd..."
cp "$SCRIPT_DIR/citofono-voip.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable citofono-voip

# Crea directory log
mkdir -p /var/log
touch /var/log/citofono-voip.log
chmod 644 /var/log/citofono-voip.log

# Riepilogo
echo ""
echo "[6/6] Verifica installazione..."
echo "  Script principale: $INSTALL_DIR/citofono-voip.py"
echo "  Configurazione:    $INSTALL_DIR/config.env"
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
echo "   sudo nano $INSTALL_DIR/config.env"
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
