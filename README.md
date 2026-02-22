# Citofono VoIP

Sistema citofono-VoIP per Raspberry Pi 3B+ che integra un citofono tradizionale Terraneo con un centralino Grandstream tramite il protocollo SIP, usando [Baresip](https://github.com/baresip/baresip) come client VoIP.

## Come funziona

1. Il citofono Terraneo viene collegato al Raspberry Pi tramite GPIO
2. Quando qualcuno suona, il sistema rileva il segnale sul pin di suoneria (interrupt o polling)
3. Viene automaticamente effettuata una chiamata SIP verso il numero configurato (interno singolo o Ring Group del centralino Grandstream)
4. Durante la conversazione, digitando un codice DTMF (default `91`) si attiva il rele per aprire il portone
5. La chiamata termina automaticamente dopo il timeout configurato

Un LED di stato opzionale indica lo stato del sistema: lampeggio lento = operativo, lampeggio rapido = errore.

## Requisiti

### Hardware

- **Raspberry Pi 3B+** (o compatibile)
- **Scheda audio USB** per microfono e altoparlante (la scheda audio onboard del RPi non ha ingresso)
- **Modulo rele** per comandare l'apertura del portone elettrico
- **Circuito di interfaccia** per collegare il segnale di suoneria del citofono Terraneo al GPIO (optoisolatore consigliato)
- **LED** di stato (opzionale)

### Software

- Raspbian / Raspberry Pi OS
- Python 3 con `RPi.GPIO`
- Baresip con moduli ALSA
- Centralino SIP (testato con Grandstream)

### Schema connessioni GPIO

Numerazione BCM. I pin sono configurabili in `config.env`.

| Pin BCM | Funzione                 | Direzione          | Nota                                       |
|---------|--------------------------|--------------------|---------------------------------------------|
| 17      | Rilevamento suoneria     | Input (pull-up)    | Collegare tramite optoisolatore al citofono |
| 27      | Comando rele portone     | Output             | Attiva il rele per aprire il portone        |
| 22      | LED stato sistema        | Output (opzionale) | Lampeggio lento = OK, rapido = errore       |

## Installazione

### Installazione automatica

```bash
git clone https://github.com/ghastx/doorpy.git
cd doorpy
sudo ./install.sh
```

Lo script esegue:

1. Installazione delle dipendenze: `python3-rpi.gpio`, `baresip`, `baresip-modules`, `alsa-utils`
2. Copia dei file `.py` in `/opt/citofono-voip/`
3. Copia di `config.env.example` in `/etc/citofono-voip/config.env` (solo se non esiste)
4. Installazione del servizio systemd `citofono-voip` (`daemon-reload` + `enable`)

### Installazione manuale

```bash
sudo apt install python3-rpi.gpio baresip baresip-modules alsa-utils
sudo mkdir -p /opt/citofono-voip
sudo cp *.py /opt/citofono-voip/
sudo mkdir -p /etc/citofono-voip
sudo cp config.env.example /etc/citofono-voip/config.env
sudo chmod 600 /etc/citofono-voip/config.env
sudo cp citofono-voip.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable citofono-voip
```

## Configurazione

Dopo l'installazione, modifica il file di configurazione:

```bash
sudo nano /etc/citofono-voip/config.env
```

### Variabili di configurazione

| Variabile             | Default                        | Descrizione                                                    |
|-----------------------|--------------------------------|----------------------------------------------------------------|
| `PIN_SUONERIA`        | `17`                           | Pin GPIO (BCM) collegato al segnale di suoneria                |
| `PIN_RELE_PORTONE`    | `27`                           | Pin GPIO (BCM) collegato al modulo rele                        |
| `PIN_LED_STATO`       | `22`                           | Pin GPIO (BCM) per il LED di stato                             |
| `SIP_USERNAME`        | `2000`                         | Username dell'interno SIP                                      |
| `SIP_PASSWORD`        | *(obbligatoria)*               | Password dell'interno SIP                                      |
| `SIP_DOMAIN`          | `centralino.ponsacco.local`    | Hostname o IP del centralino                                   |
| `SIP_PORT`            | `5060`                         | Porta SIP (UDP)                                                |
| `NUMERO_DA_CHIAMARE`  | `6400`                         | Numero o Ring Group da chiamare alla suoneria                  |
| `DTMF_APRI_PORTONE`   | `91`                           | Codice DTMF per aprire il portone durante la chiamata          |
| `DEBOUNCE_SUONERIA_MS`| `300`                          | Debounce del segnale di suoneria (millisecondi)                |
| `DURATA_APERTURA`     | `2`                            | Durata attivazione rele (secondi)                              |
| `TIMEOUT_CHIAMATA`    | `60`                           | Timeout massimo della chiamata (secondi)                       |
| `AUDIO_PLAY_DEVICE`   | `hw:1,0`                       | Dispositivo ALSA per riproduzione                              |
| `AUDIO_REC_DEVICE`    | `hw:1,0`                       | Dispositivo ALSA per registrazione                             |
| `LOG_FILE`            | `/var/log/citofono-voip.log`   | Percorso del file di log                                       |

Vedi `config.env.example` per una descrizione dettagliata di ogni variabile.

### Configurazione Grandstream

Sul centralino Grandstream:

1. Crea un **interno SIP** dedicato al citofono (es. interno 2000)
2. Annota username e password da inserire in `config.env`
3. Crea un **Ring Group** (es. 6400) che faccia squillare gli interni desiderati
4. Verifica che l'interno del citofono risulti **registrato** dopo l'avvio del servizio

## Utilizzo

### Avvio come servizio

```bash
# Avvia il servizio
sudo systemctl start citofono-voip

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

## Risoluzione problemi

### Audio non funziona

- Elenca i dispositivi disponibili:
  ```bash
  aplay -l     # riproduzione
  arecord -l   # registrazione
  ```
- Verifica che la scheda USB sia riconosciuta (tipicamente come `card 1`)
- Se la scheda ha un numero diverso, aggiorna `AUDIO_PLAY_DEVICE` e `AUDIO_REC_DEVICE` in `config.env`
- Regola i livelli con `alsamixer -c 1`
- Esegui `test_audio.sh` per verificare registrazione e riproduzione

### Problemi SIP / interno non si registra

- Verifica che il centralino sia raggiungibile:
  ```bash
  ping centralino.ponsacco.local
  ```
- Controlla che username e password in `config.env` corrispondano a quelli configurati sul Grandstream
- Verifica che la porta SIP (default 5060/UDP) non sia bloccata dal firewall
- Controlla i log per errori di registrazione:
  ```bash
  sudo journalctl -u citofono-voip --no-pager -n 50
  ```

### Suoneria non rilevata

- Esegui `test_suoneria.py` e verifica che il segnale venga rilevato
- Controlla il circuito di interfaccia (optoisolatore) tra citofono e GPIO
- Se l'interrupt non funziona, lo script passa automaticamente a polling (vedi log)
- Verifica che `PIN_SUONERIA` in `config.env` corrisponda al pin effettivamente collegato

### Il servizio non parte

```bash
sudo journalctl -u citofono-voip --no-pager -n 50
```

Cause comuni:
- `SIP_PASSWORD` non impostata in `config.env`
- Baresip non installato (`sudo apt install baresip baresip-modules`)
- Permessi insufficienti (il servizio deve girare come root per accedere ai GPIO)

## Struttura del progetto

```
doorpy/
├── LICENSE                 # Licenza GPL-2.0
├── README.md               # Questo file
├── config.env.example      # Template configurazione
├── citofono-voip.py        # Script principale
├── citofono-voip.service   # Unit file systemd
├── install.sh              # Script di installazione
├── requirements.txt        # Dipendenza Python: RPi.GPIO
├── test_portone.py         # Test rele portone
├── test_suoneria.py        # Test rilevamento suoneria
└── test_audio.sh           # Test dispositivi audio
```

## Licenza

Questo progetto e distribuito sotto licenza **GNU General Public License v2.0 o successiva** - vedi il file [LICENSE](LICENSE) per i dettagli.
