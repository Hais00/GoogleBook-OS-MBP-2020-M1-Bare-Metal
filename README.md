# GoogleBook OS MBP 2020 M1 Bare-Metal

Port sperimentale di Android per **MacBook Pro 13″ 2020 M1, J293 / t8103**, con driver nativi Apple/Asahi e adattamenti Android per grafica, input, Wi-Fi e audio.

Questa prima pubblicazione raccoglie i sorgenti del port, le modifiche rispetto agli upstream e le note di avvio. **Le sessioni documentate hanno usato l’hypervisor di debug m1n1 per conservare la UART via USB. L’avvio diretto senza quel livello di debug non è ancora qualificato.** Il nome Bare-Metal esprime l’obiettivo del progetto; GPU, display, storage e audio usano percorsi hardware nativi.

La riproduzione esatta dell’intera immagine verrà consolidata successivamente. Questa repository contiene codice e ricette di sviluppo, non un’immagine Android pronta da installare. Il sistema Android di partenza e il firmware Apple devono essere ottenuti separatamente; non sono redistribuiti qui.

## Stato del port

| Area | Riscontro disponibile |
| --- | --- |
| Avvio Android | Boot completo e interfaccia sul J293 con kernel Asahi e profilo a pagine da 16 KiB, durante sessioni m1n1 di debug. |
| Display e OpenGL | Percorso nativo DRM/HWC, gralloc e Mesa Asahi già utilizzato sul dispositivo. |
| Vulkan | Honeykrisp: AHardwareBuffer import/export, otto prove di dipendenza tra due code native e quattro frame di swapchain verificati sul M1. Impostazioni ha prodotto 97 frame Skia Vulkan e testo/icone sono stati confermati visivamente. |
| Vulkan in SurfaceFlinger | L’attivazione completa ha riprodotto un errore di priorità. La nuova correzione kernel/Mesa è compilata e verificata localmente; **la validazione hardware è sospesa su richiesta del proprietario**. |
| Wi-Fi | Connessione a una rete confermata sul dispositivo. |
| Bluetooth audio | Riproduzione nelle cuffie confermata dall’utente. L’integrazione usa anche componenti audio dell’immagine Android originale. |
| Speaker | Riproduzione confermata con il servizio ALSA/AIDL nativo, quattro canali fisici a 48 kHz e protezione speakersafetyd. Il limite digitale del port rimane 0,125; DSP completo e durata termica non sono qualificati. |
| Tastiera e Touch Bar | Percorsi LED/PWM, ADP e uinput implementati; funzionamento della Touch Bar e correzione visiva delle icone riscontrati sul dispositivo. Il cursore Android per la retroilluminazione per singola tastiera resta un’integrazione separata. |
| Video hardware | Il decoder AVD è compilato e i nodi video/media sono stati registrati. Android seleziona ancora codec `c2.android.*` software: manca l’adattatore Codec2 per V4L2 Request stateless. L’encoder hardware non è collegato. |

I risultati delle versioni precedenti non qualificano automaticamente una nuova build. [Stato e verifiche](docs/status.md) distingue le prove già svolte dalle parti ancora aperte.

## Percorso di avvio documentato

```text
iBoot → proxy m1n1 originale via USB
      → m1n1 di debug con UART virtuale
      → kernel Linux Asahi e initramfs caricati in RAM
      → bootstrap e partizioni Android sul NVMe interno
      → init Android, HAL e interfaccia
```

L’installer di sviluppo confronta il prefisso delle partizioni, verifica la copia di ripristino dell’area inattiva, scrive il payload selezionato e ne confronta la rilettura. Solo dopo verifica e aggiorna le quattro copie dei metadati liblp. I sorgenti sono in `scripts/build_ram_bootstrap.py`, `scripts/m1_ram_image_update.py` e negli strumenti di staging.

Le ricette pubblicate contengono percorsi schematici `/opt/googlebook/...` e UUID di esempio. Le corrispondenze tra partizioni senza nome e `super`, `metadata`, `userdata` devono essere configurate per l’installazione effettiva. Le procedure private di prenotazione della UART, i backup e i log integrali non fanno parte di questa pubblicazione.

## Modifiche necessarie per arrivare al boot

- **Kernel:** profilo Apple con pagine da 16 KiB, Binder e dipendenze Android; compatibilità memfd/ashmem; assegnazione dei nomi alle partizioni Android non nominate senza riscrivere GPT; correzioni DRM fence; adattamenti della compilazione sul Mac; correzione pitch/allocazione ADP per lo scanout.
- **Grafica Android:** minigbm e drm-hwcomposer adattati ai dispositivi DRM effettivi, separando display principale e Touch Bar. Mesa Asahi fornisce OpenGL; Honeykrisp aggiunge il percorso Android native-buffer/AHardwareBuffer e la sincronizzazione della presentazione.
- **Code Vulkan:** due code native con worker distinti. Le dipendenze reali vengono attese prima del lock che protegge gli heap condivisi. L’esecuzione GPU del percorso resta serializzata per correttezza: non viene dichiarato parallelismo GPU.
- **Priorità Vulkan:** supporto kernel `CAP_SYS_NICE` e discovery per chiamante, inoltro della priorità reale e propagazione degli errori. La modifica è descritta in [Priorità GPU](docs/gpu-priorities.md).
- **Componenti Android:** sostituzione o disattivazione mirata di percorsi Qualcomm non pertinenti, servizi Linux per Wi-Fi/USB/Bluetooth, adattamenti VINTF e SELinux mirati. I test sul target hanno mantenuto SELinux Enforcing.
- **Input:** servizio Lights compatibile con le interfacce AOSP effettive, renderer Touch Bar su ADP e input uinput; gestione dei contatti, dei cambi di layout e delle completion di page flip.
- **Audio:** modulo primario AIDL/ALSA, configurazione AppleJ293 a 48 kHz, mapping fisico a quattro canali, FIR e interlock degli speaker. Correzioni dell’indirizzo AIDL della porta, recupero XRUN e gestione pausa/flush senza fingere frame presentati.
- **Trasporto di debug:** corretti la chiusura dei pipe ereditati e il riconoscimento di EOF nelle risposte 9P del client host m1n1, evitando attese indefinite quando l’exporter viene rifiutato.
- **Framework OEM:** gli adattamenti limitati delle prime fasi sono descritti nelle note storiche; i JAR e gli altri binari proprietari modificati non vengono redistribuiti.
- **Decoder AVD:** firmware open source Asahi e linker Cortex-M3 corretto per collocare i vettori all’indirizzo zero. Questo prepara il driver; non sostituisce il componente Codec2 mancante.

Le parti software/non-secure di KeyMint e Gatekeeper sono codice di bring-up: non attestano un’implementazione della sicurezza hardware Apple o un prodotto Android certificato.

## Sorgenti e patch

- [`sources/`](sources/): snapshot dei file upstream modificati, compresi kernel, Mesa, minigbm, drm-hwcomposer, ALSA e speakersafetyd.
- [`scripts/`](scripts/): implementazioni locali C/C++, helper, ricette di build/staging e test.
- [`patches/`](patches/README.md): modifiche applicabili ai commit upstream registrati.
- [`upstream/`](.gitmodules): riferimenti Git ai progetti completi, fissati a commit espliciti.
- [`config/kernel25.config`](config/kernel25.config): configurazione del kernel costruito localmente.
- [`manifests/`](manifests/): commit, hash dei sorgenti ed eventuali adattamenti per la pubblicazione.
- [`docs/`](docs/README.md): stato attuale e note tecniche, incluse le fasi storiche.

La configurazione delle dipendenze e l’unificazione delle ricette in un build riproducibile restano lavoro successivo. Gli upstream possono essere recuperati con `git submodule update --init`: il kernel ha una cronologia voluminosa.

## Licenze e provenienza

Il glue originale del port e la documentazione seguono [LICENSE](LICENSE), salvo indicazione diversa nei singoli file. I componenti derivati mantengono le proprie licenze: **il kernel e speakersafetyd non vengono riclassificati come MIT**. Vedere [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) e [LICENSES](LICENSES/).

Nessun binario Android/Google, firmware Apple, chiave, credenziale, backup o capture UART privata è incluso. L’interfaccia audio desktop Rust di Google rimane una dipendenza binaria esterna dell’immagine usata nelle prove; questa repository non ne contiene né ricostruisce il sorgente.
