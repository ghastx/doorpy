# Citofono VoIP

Sistema citofono-VoIP per Raspberry Pi 3B+ che integra un citofono tradizionale Terraneo con un centralino Grandstream tramite il protocollo SIP, usando [Baresip](https://github.com/baresip/baresip) come client VoIP.

## Come funziona

1. Il citofono Terraneo viene collegato al Raspberry Pi tramite GPIO
2. Quando qualcuno suona, il sistema rileva il segnale sul pin di suoneria (interrupt o polling)
3. Viene automaticamente effettuata una chiamata SIP verso il numero configurato (interno singolo o Ring Group del centralino Grandstream)
4. Durante la conversazione, digitando un codice DTMF (default `*9`) si attiva il rele per aprire il portone
5. La chiamata termina automaticamente dopo il timeout configurato

Un LED di stato opzionale indica lo stato del sistema: lampeggio lento = operativo, lampeggio rapido = errore.

## Requisiti hardware

- **Raspberry Pi 3B+** (o compatibile)
- **Scheda audio USB** per microfono e altoparlante (la scheda audio onboard del RPi non ha ingresso)
- **Modulo rele** per comandare l'apertura del portone elettrico
- **Circuito di interfaccia** per collegare il segnale di suoneria del citofono Terraneo al GPIO (optoisolatore consigliato)
- **LED** di stato (opzionale)

### Collegamento GPIO (BCM)

| Pin | Funzione | Direzione | Default |
|-----|----------|-----------|---------|
| 17  | Rilevamento suoneria | Input (pull-up) | `PIN_SUONERIA` |
| 27  | Comando rele portone | Output | `PIN_RELE_PORTONE` |
| 22  | LED stato sistema | Output | `PIN_LED_STATO` |

I pin sono configurabili in `config.env`.

## Installazione

### Installazione automatica

```bash
git clone https://github.com/ghastx/doorpy.git
cd doorpy
sudo ./install.sh
```

Lo script esegue:

1. Aggiornamento del sistema (`apt update && apt upgrade`)
2. Installazione delle dipendenze: `baresip`, `baresip-core`, `python3-rpi.gpio`, `alsa-utils`, `libasound2-dev`
3. Configurazione ALSA con la scheda audio USB come dispositivo default
4. Copia dei file in `/opt/citofono-voip/`
5. Creazione del servizio systemd `citofono-voip`
6. Installazione degli script di test

### Installazione manuale

```bash
sudo apt install baresip baresip-core python3-rpi.gpio alsa-utils libasound2-dev
sudo mkdir -p /opt/citofono-voip
sudo cp citofono-voip.py config.env.example /opt/citofono-voip/
sudo cp config.env.example /opt/citofono-voip/config.env
sudo chmod 600 /opt/citofono-voip/config.env
sudo cp citofono-voip.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable citofono-voip
```

## Configurazione

Dopo l'installazione, modifica il file di configurazione:

```bash
sudo nano /opt/citofono-voip/config.env
```

### Parametri principali

```env
# Credenziali SIP per la registrazione sul centralino
SIP_USERNAME=2000
SIP_PASSWORD=changeme
SIP_DOMAIN=centralino.ponsacco.local
SIP_PORT=5060

# Numero da chiamare quando suona il citofono
# Puo essere un interno singolo o un Ring Group del Grandstream
NUMERO_DA_CHIAMARE=6400

# Codice DTMF che l'utente digita per aprire il portone
DTMF_APRI_PORTONE=*9
```

### Parametri opzionali

```env
# GPIO (BCM) - modifica solo se il cablaggio e diverso
PIN_SUONERIA=17
PIN_RELE_PORTONE=27
PIN_LED_STATO=22

# Timing
DURATA_APERTURA=2        # Secondi di attivazione rele
TIMEOUT_CHIAMATA=60      # Secondi prima di riagganciare

# Audio (verifica con 'aplay -l' e 'arecord -l')
AUDIO_PLAY_DEVICE=hw:1,0
AUDIO_REC_DEVICE=hw:1,0

# Log
LOG_FILE=/var/log/citofono-voip.log
```

### Configurazione Grandstream

Sul centralino Grandstream:

1. Crea un **interno SIP** dedicato al citofono (es. interno 2000)
2. Annota username e password da inserire in `config.env`
3. Crea un **Ring Group** (es. 6400) che faccia squillare gli interni desiderati
4. Verifica che l'interno del citofono risulti **registrato** dopo l'avvio del servizio

## Utilizzo

### Avvio del servizio

```bash
sudo systemctl start citofono-voip
```

### Comandi utili

```bash
# Stato del servizio
sudo systemctl status citofono-voip

# Log in tempo reale
sudo journalctl -u citofono-voip -f

# Riavvio
sudo systemctl restart citofono-voip

# Arresto
sudo systemctl stop citofono-voip

# Disabilita avvio automatico
sudo systemctl disable citofono-voip
```

### Avvio manuale (debug)

```bash
sudo python3 /opt/citofono-voip/citofono-voip.py
```

## Test dei componenti

Prima di avviare il servizio, verifica che ogni componente funzioni correttamente.

### Test audio

Registra 5 secondi dal microfono e li riproduce sull'altoparlante:

```bash
sudo /opt/citofono-voip/test_audio.sh
```

Se i livelli non sono corretti, regolali con:

```bash
alsamixer -c 1
```

### Test suoneria

Monitora il pin GPIO della suoneria e stampa un messaggio quando rileva il segnale:

```bash
sudo python3 /opt/citofono-voip/test_suoneria.py
```

Fai suonare il citofono e verifica che venga rilevato. `Ctrl+C` per uscire.

### Test rele portone

Attiva il rele per 2 secondi (default) o per una durata specificata:

```bash
sudo python3 /opt/citofono-voip/test_portone.py        # 2 secondi
sudo python3 /opt/citofono-voip/test_portone.py 5       # 5 secondi
```

## Struttura del progetto

```
doorpy/
├── LICENSE                 # Licenza GPL-2.0
├── README.md               # Questo file
├── .gitignore
├── requirements.txt        # Dipendenza Python: RPi.GPIO
├── config.env.example      # Template configurazione
├── citofono-voip.py        # Script principale
├── citofono-voip.service   # Unit file systemd
├── install.sh              # Script di installazione
├── test_portone.py         # Test rele portone
├── test_suoneria.py        # Test rilevamento suoneria
└── test_audio.sh           # Test dispositivi audio
```

## Risoluzione problemi

### Il servizio non parte

```bash
sudo journalctl -u citofono-voip --no-pager -n 50
```

Cause comuni:
- `SIP_PASSWORD` non impostata in `config.env`
- Baresip non installato (`sudo apt install baresip baresip-core`)
- Permessi insufficienti (il servizio deve girare come root per accedere ai GPIO)

### L'interno non si registra sul centralino

- Verifica che `SIP_DOMAIN` sia raggiungibile: `ping centralino.ponsacco.local`
- Controlla che username e password corrispondano a quelli configurati sul Grandstream
- Verifica che la porta SIP (default 5060/UDP) non sia bloccata dal firewall

### Audio non funziona

- Elenca i dispositivi: `aplay -l` e `arecord -l`
- Verifica che la scheda USB sia riconosciuta come `card 1`
- Se la scheda ha un numero diverso, aggiorna `/etc/asound.conf` e `AUDIO_PLAY_DEVICE` / `AUDIO_REC_DEVICE` in `config.env`

### Suoneria non rilevata

- Esegui `test_suoneria.py` e verifica il segnale
- Controlla il circuito di interfaccia (optoisolatore) tra citofono e GPIO
- Se l'interrupt non funziona, lo script passa automaticamente a polling

## Licenza

Questo progetto e distribuito sotto licenza **GNU General Public License v2.0** - vedi il file [LICENSE](LICENSE) per i dettagli.
