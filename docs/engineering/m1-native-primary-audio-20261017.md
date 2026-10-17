> Historical engineering notes. The current status is in ../../README.md and ../../docs/status.md; earlier candidate/pending sections describe their original phase.

# HAL primario ALSA M1 J293

Implementato un servizio autonomo `android.hardware.audio.core.IModule/m1`, con API AOSP V3 congelata e hash originale `eb5f1f5af402830af56b50eb66bdd60fd8cc774e`. Mantiene invariati i servizi e le librerie Google originali che forniscono Bluetooth. Non pubblica microfoni, MMAP, offload o altri percorsi non implementati.

## Percorso reale

Il servizio riconosce la scheda tramite identità ALSA `AppleJ293`/`macaudio`, verifica sul PCM le capacità S32_LE, quattro canali e 48 kHz, configura la route Secondary prevista dall’UCM Asahi e pubblica una porta primaria stereo PCM16 a 48 kHz. Il framework può così costruire un AudioPolicyManager valido e gestire anche le uscite Bluetooth.

Lo stream usa i worker Binder/FMQ AOSP e scrive realmente ALSA. Il drain viene richiesto una sola volta: in modalità non bloccante, ripeterlo aggiungerebbe ulteriore silenzio nel plugin hw. Il completamento viene ricontrollato nello stato kernel DRAINING → SETUP; errori e timeout restano errori. Le posizioni vengono ricavate dai frame inviati e dal ritardo ALSA, senza conteggiare come presentati i frame scartati.

Il DSP applica le FIR front/rear J293 a 48 kHz ai quattro canali FL/FR/RL/RR. Questa prima integrazione impone un picco digitale massimo di 0,125, circa −18 dBFS: la piena catena di effetti e compressione PipeWire/LSP non è stata portata né qualificata. Non dichiarare equivalente l’intero DSP Asahi o disponibile il volume massimo originale.

## Protezione

`speakersafetyd` resta una dipendenza GPL separata, con sorgente, licenza e patch riproducibili conservati. Usa il profilo J293 originale, gli otto canali V/I del PCM2, il modello termico, i lock dei controlli e il keepalive originali. Gli adattamenti sono il flag di avvio su tmpfs `/dev/speakersafetyd` e il percorso sysfs diretto alla stessa proprietà DT `compatible`.

L’HAL non scrive mai il magic di sblocco né i guadagni degli amplificatori. Prima dei campioni del client verifica il vero controllo kernel `Speaker Volume Unlock`; se necessario avvia il clock con soli zeri entro un timeout. Alla perdita dello sblocco chiude il PCM e restituisce errore. Il kernel mantiene il clamp originale.

La policy aggiunge una sola etichetta per `compatible` e una per il flag temporaneo, con permessi mirati del dominio audio. Nessun permissive sul target, nessun cambiamento dei permessi dei nodi audio e nessuna modifica al kernel23 o ai componenti Wi-Fi/Touch Bar.

## Verifiche completate

- Compilazione Bionic del servizio e della protezione, ELF AArch64 e allineamento 16 KiB.
- Prova reale in VM kernel23: Binder remoto V3, FMQ, PCM ALSA loopback, 19.200 frame accettati e presentati dopo drain; quattro canali confrontati con i campioni client. Il loopback è presente esclusivamente nel banco CPU, non nell’immagine installabile.
- Esecuzione Bionic di help/version della protezione; rifiuto della mancanza hardware prima dei controlli. Questo non qualifica il modello termico sul silicio.
- Compilazione della policy completa con secilc e neverallow attivi: RC0.
- EROFS: 3.380 inode e 2.797 payload confrontati con archivio, UID/GID, modi, link, tipi e xattr. Lettura e hash di tutti i file anche con il kernel23 di produzione.

Immagine `vendor-generation13-native-audio-r2.erofs`, 404.697.088 byte, SHA-256 `0fbc54ccfe5bec06756a13ac537654e6ac37057b5e38b640d79077164382b815`.

## Verifica M1 pendente

Non installata al momento di questa nota. Il precedente collegamento è terminato il 17 ottobre alle 13:28:35 Europe/Rome con errore USB ENODEV; nessun riavvio richiesto da questo lavoro e causa non stabilita. Il log Android iniziale da 16 MB e i log UART/HV sono salvati e sigillati. Resta da recuperare il file `/data/local/tmp/gos-audio13-preparation-full.log`.

Prima dell’avvio: controllare il proxy originale, rileggere il prefisso NVMe corrente e confrontarlo con quello atteso; archivio inattivo vendor11 verificato sul target prima della scrittura. Preservare vendor12 attivo e vendor10 stabile. Poi provare SELinux enforcing, processo di protezione, reale AudioPolicyManager, porte Bluetooth, stream e ascolto.

## Revisione finale R2

Mute e volume master non sono controlli hardware implementati: il servizio restituisce esplicitamente unsupported, così AudioFlinger applica il proprio mixer software. Il test remoto verifica anche il rifiuto dei falsi ACK. R8 conferma nuovamente 19.200 frame reali e il confronto dei quattro canali. L’immagine R1 non è mai stata installata.

Tutti i controlli locali della R2 sono PASS. Il piano è congelato e verificato su file sparso privato; l’ammissione hardware rimane falsa fino alla rilettura fisica del prefisso NVMe. Il 17 ottobre l’utente ha indicato il proxy pronto, ma il Mac di lavoro non enumera ancora m1n1 né le sue due porte USB. Nessuna prova fisica o scrittura del nuovo vendor è stata dichiarata.

## Prova reale definitiva: vendor14

La prima prova hardware vendor13 ha rilevato un difetto di conversione: l’indirizzo AIDL `alsa(card,device)` dello speaker interno diventava un indirizzo `id` nel percorso legacy Android e non corrispondeva più alla porta pubblicata. Vendor14 usa l’indirizzo interno canonico AOSP `id("")`; la selezione reale di scheda e PCM rimane nel backend ALSA qualificato. Nessuna sostituzione del framework o modifica delle librerie Google.

Immagine installata: `vendor-generation14-native-audio-r1.erofs`, 404.701.184 byte, SHA-256 `8c688b41ec297f31cf0f1f536756f14ffd2a17fc0cf52d91a58f480142e89fc8`. Sul M1: archivio vendor12 confrontato col disco, payload riletto e quattro copie LP committate con successo; precedente vendor13 e vendor10 stabile conservati. Il passaggio da 13 a 14 è avvenuto tramite `/system/bin/reboot` Android, senza reset del proxy.

Android completa il boot con SELinux Enforcing. Il framework apre realmente il primario m1 a 48 kHz; la porta speaker è ID4 e l’I/O primario è 13. La prova pubblica AAudio ha selezionato e ricontrollato ID4, accettato 48.000 frame stereo a 48 kHz ed è uscita con codice0. AudioFlinger registra successivamente 69.632 frame scritti, nessun underrun del mixer e ritorno in standby. I processi HAL593 e protezione585 restano attivi nel dominio audio; il kernel ha registrato lo sblocco reale degli speaker.

Evidenze: `trial-native-audio-kernel23-v14-r1/hardware-audio-result.json` e file citati nel suo elenco. Il log Android completo della prova è salvato sul host con confronto SHA-256 (5.607.424 byte, `5aa1b8ed4f498232fd305622b94b49e620edbd3d6b5cf3ae6315a1bd3e8f7c26`); il logger completo sul target continua su un nuovo file, con sovrapposizione temporale.

La conferma dell’ascolto dell’utente è ancora pendente: frame accettati e DMA attivo non vengono descritti come prova acustica. Bluetooth è ON senza crash e mantiene una cuffia abbinata, ma non è ancora connessa nella prova14. Il trasferimento e l’ascolto nelle cuffie restano da verificare. Il limite speaker 0,125 e la mancata qualifica della piena catena LSP restano invariati.


## Riscontro acustico e correzione XRUN / MCA pause

Il 17 ottobre l’utente conferma che le cuffie Bluetooth suonano con Spotify. Gli speaker sono invece silenziosi anche con Spotify effettivamente assegnato alla porta 4. Il log completo verificato `android-full-8d3b7e655e.log` mostra alle 14:47:10.063 `write failed: -32` e alle 14:47:11.528 il rifiuto di standby dallo stato ERROR. I frame accettati prima del guasto non qualificavano la stabilità né l’acustica.

La nuova implementazione recupera un vero XRUN con prepare ALSA e ricontrolla la protezione prima dei campioni; gli altri errori non diventano successi. Mantiene conservativamente l’ultima posizione osservata prima del reset del PCM, senza dichiarare riprodotti campioni non osservati. MCA non dichiara INFO_PAUSE: la pausa usa stop reale, puntatori congelati e coda limitata per conservare la coda pendente; flush la scarta, resume la riemette solo dopo verifica della protezione. Diagnostica in sola lettura di controlli, owner/lock, PCM, recuperi e picchi.

Regressione CPU con Bionic/Binder/FMQ e snd-aloop reale: vecchio binario riproduce EPIPE e stato ERROR; correzione supera starvation di 220 ms, burst vuoto, ripresa con campioni riletti, pausa con backpressure, resume, drain, standby/reopen e sequenza Android pause→flush→standby. `native-primary-audio-local-runtime-r9-xrun-pause/result.json` PASS. Nessuna prova CPU è una qualifica acustica del J293. Picco massimo 0,125 e speakersafetyd invariati. Installazione e prova hardware della nuova immagine ancora pendenti.


Riscontro hardware finale native15: installazione con archivio13 verificato sul Mac, immagine riletta e tutte le copie LP PASS. Android boot_completed=1 e SELinux Enforcing. L’utente conferma che Spotify suona ora dagli altoparlanti interni. Cuffie Bluetooth già confermate udibili sulla versione14. Limite di picco e protector invariati; non è una qualifica della catena DSP completa o della durata.
