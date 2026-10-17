> Historical engineering notes. The current status is in ../../README.md and ../../docs/status.md; earlier candidate/pending sections describe their original phase.

# Audio Bluetooth M1 — integrazione del 17 ottobre 2026

## Stato

Configurazione preparata e percorso Binder verificato localmente. Prova M1 autorizzata e in preparazione. Riproduzione nelle cuffie, FMQ PCM e HFP sul controller fisico ancora da verificare. Gli altoparlanti interni non sono qualificati.

## Diagnosi verificata

Il servizio C++ originale `dras.core-cpp.audio` esiste nell’APEX audio e si avviava già sul M1, ma pubblicava solamente `IModule/r_submix`. Non mancava il programma: erano disattivati il ramo Bluetooth software e la relativa configurazione.

Il costruttore desktop `ModuleBluetooth` del binario originale ottiene `com.android.desktop.audio.IDesktopAudioFactory/default` nel processo Rust e registra la factory audio Bluetooth. Questo collegamento Binder previsto dall’immagine permette di usare i provider software Rust senza inserire una factory AOSP indipendente con un altro proprietario della sessione.

## Modifiche candidate

Stage: `.agent-work/vendor-audio-stage`, derivato dal vendor10 Wi-Fi verificato.

- Attivazione del percorso software HFP richiesto dal servizio C++ per creare il modulo Bluetooth; offload Qualcomm A2DP/LE disattivato.
- Inclusione del modulo Bluetooth con porte SCO esterne e delle route A2DP; sintassi delle liste XML normalizzata.
- Avvio tramite il programma C++ dell’APEX originale, con dichiarazioni init delle interfacce e VINTF `IModule/bluetooth` V4.
- `/dev/rfkill` assegnato a `bluetooth:bluetooth`, modo 0660, tipo SELinux esistente `bt_device`. Nessuna nuova regola allow e nessuna modifica al CIL.

Nessun ELF è cambiato rispetto al vendor10. L’APEX Google resta identico. Il binario Rust installato conserva l’adattamento preesistente del nome `libagmipcservice.so` a `libgosagmservice.so`; questa fase non lo aggiunge né lo estende. La configurazione primaria `vendor.audio.dras.default_nothing=true` resta attiva: non costituisce un HAL nativo per gli altoparlanti interni.

## Test locali effettivi

Kernel23 reale in VM senza dischi fisici, radio o dispositivi audio esposti; Bionic e Binder reali, processi audio forniti senza modifiche.

- Positivo: quattro owner reali disponibili (`IModule/default`, `IModule/a2dp`, `IDesktopAudioFactory/default`, `IModule/r_submix`); factory V6; una capacità A2DP software; apertura e ping di un provider Binder remoto riusciti.
- Negativo: disabilitando il percorso HFP software, gli stessi quattro owner restano disponibili ma la factory Bluetooth non viene registrata.
- Le prove non trasferiscono ancora PCM e non qualificano radio, pairing, cuffie, microfono, HFP o la policy enforcing su M1. La VM usa la policy Android salvata in modalità permissiva solo nel banco di prova, con processi in contesto kernel; i programmi e gli helper della prova non entrano nello stage vendor.

Evidenze: `/opt/googlebook/external/googlebook-bringup-20261016/audio-software-local-runtime-r11/result.json` e `/opt/googlebook/external/googlebook-bringup-20261016/audio-software-local-runtime-negative/result.json`.

## Ammissione hardware

Completare immagine EROFS e confronto di tutti i payload, owner, modi e xattr; lettura completa con kernel23; piano limitato a vendor_a con vendor10 attivo preservato. Il vecchio extent inattivo generation7 può essere riutilizzato solo dopo archivio esatto verificato anche sul target, prima di aprire il dispositivo in scrittura. Nessuna scrittura su GPT, macOS, ESP o userdata.

I tentativi iniziali di packaging locale non sono ammessi all’installazione. La variante finale è stata costruita su un filesystem ext4 in un disco virtuale locale usa e getta, con lettura sequenziale dell’archivio (`--sort=none`), evitando il file sparso provvisorio da 2 TiB su APFS e i limiti della tmpfs. Il filesystem verificato contiene 3.273 inode e 2.699 file regolari: tutti i payload, UID/GID, modi, tipi, destinazioni dei link e xattr di sicurezza corrispondono all’archivio sorgente.

Immagine: `vendor-generation11-btaudio-r2.erofs`, 402.702.336 byte, SHA-256 `e9cb0d86f4716b37ab0e506a152306b72fdeda5acb76c5a81428dea12b9c0b9e`. Il primo scanner aveva osservato una directory vuota per un bind non ricorsivo e non costituisce una prova valida; il readback completo esplicito di 3.273 elementi è quello confrontato con l’archivio.

Sul M1 verificare log completi, enforcing=1, etichetta e accesso rfkill, stato Bluetooth ON, factory V6 e pairing. L’utente esegue personalmente l’abbinamento delle cuffie e comunicherà quando sono collegate. Solo allora qualificare route, sessione e riproduzione. Non sbloccare gli amplificatori interni senza la protezione Asahi.

## Prima prova M1 e correzione HCI

Il vendor11 è stato installato con archivio del vecchio extent, readback SHA-256 e commit LP verificati. Su M1: boot completato, SELinux Enforcing, `/dev/rfkill` 0660 bluetooth:bluetooth e `bt_device`, factory audio e `IModule/bluetooth` presenti. Il processo Bluetooth è terminato perché il trasporto AOSP15 eseguiva `rfkill(1)` prima del bind HCI USER: il kernel ha restituito `Operation not possible due to RF-kill`. Questa è una prova negativa reale, non un guasto dedotto della scheda.

Il riferimento AOSP `aa229558cbf04bc997ed27465c5e7ad497123d1b`, `bluetooth/aidl/default/net_bluetooth_mgmt.cpp`, contiene già la correzione: `rfkill(0)` prima del bind e `rfkill(1)` dopo la chiusura. Il builder verifica che il file differisca dalla versione precedente solo per queste due chiamate e i commenti, usa il vecchio header e mantiene l’interfaccia Binder V1 congelata. Nessun ACK o successo forzato.

Vendor12 cambia solo il binario HCI rispetto a vendor11. Binario SHA-256 `4e568427111954444798ba849e37ce23075f84de741b6c6ac7893e179d718bc0`; immagine 402.702.336 byte, SHA-256 `1716fccb526416830f11d047ed5db6fd3c042cc5d10cfbc015878adc1b900015`. Confronto completo di 3.273 inode e lettura di ogni payload con kernel23 superati. Il piano preserva vendor11 e il vendor10 Wi-Fi; il vecchio vendor9 viene archiviato e verificato prima del riuso. Il prefisso fisico dopo il riavvio Android coincide con quello atteso.

RUN11 è sigillato; recuperato anche il file completo della precedente prova Wi-Fi (48.074.752 byte). RUN12 è in installazione; Bluetooth ON e audio nelle cuffie restano da verificare.

## Cuffie collegate: blocco primario verificato su M1

Vendor12 avviato correttamente: Bluetooth ON senza nuovi crash, HCI inizializzato e cuffie collegate realmente nei profili HEADSET e A2DP. Wi-Fi ancora VALIDATED. SELinux resta Enforcing.

La riproduzione **non è risolta**. Il dump AudioPolicy restituisce `AudioPolicyManager: 0x0`; il log originale di audioserver contiene `The policy configuration does not declare a primary output`. Il servizio Rust dichiara `Using nothing HAL`. La configurazione XML legacy aggiunta non crea un'uscita primaria dentro il modulo AIDL Nothing: serve un proprietario primario reale con porte, route e stream ALSA. Non attribuire il mancato output al pairing né alla sola frequenza di campionamento. I 48 kHz indicati dall'utente sono un requisito utile per la futura qualifica del PCM, non una prova di funzionamento attuale.

Evidenze: `trial-native-btaudio-kernel23-v12-r3/audio-routing-diagnosis.json`, dump delle route e log completo `android-full-b21b2a7dac.log` (16.003.072 byte, SHA-256 `bc63646dd32b4b78cef84c3874f4408ce04910b55694369cbf04fe54efb784a7`). Il logger completo sul target è stato riaperto su file dopo la copia, mantenendo la UART kernel continua.

### Preparazione locale successiva, non installata

- `build_m1_speakersafetyd.py`: dipendenza Asahi GPL separata compilata per Bionic, stesso modello, sensori V/I, ownership dei controlli e keepalive; soltanto il flag di boot passa da `/run` a una directory tmpfs `/dev/speakersafetyd`, che dovrà essere creata da init. Il servizio non è stato avviato sul M1 e gli amplificatori non sono stati sbloccati.
- `test_m1_speaker_dependency_runtime.py`: esecuzione reale in VM con kernel23 e Bionic; version/help superati, assenza hardware rifiutata prima di accedere ai controlli. Nessun dispositivo audio o disco fisico nella VM. È uno smoke test delle dipendenze, non una qualifica del modello termico o della riproduzione.
- `fetch_m1_native_audio_references.py` e `build_m1_native_audio_abi.py`: fonti AOSP fissate e otto librerie Binder generate dai veri snapshot congelati (core V3, common types V4 e dipendenze). Destinate a un processo nativo separato; nessuna modifica dei metadati versione/hash, nessuna sostituzione delle librerie originali Google. **Non costituiscono ancora l'implementazione di un servizio HAL primario.**

Restano implementazione e verifica del servizio primario ALSA, PCM e posizioni/drain reali, routing J293, integrazione init/SELinux della protezione e prove hardware. Non usare una falsa uscita speaker o un backend che scarta campioni per superare l'inizializzazione del gestore audio.
