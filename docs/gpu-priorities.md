# Priorità GPU native

La correzione coinvolge il driver Asahi nel kernel e Honeykrisp in Mesa. È una modifica locale del port, distinta dalle release upstream di entrambi.

## Problema riprodotto

Il driver Vulkan dichiarava LOW, MEDIUM, HIGH e REALTIME, ma rifiutava incondizionatamente le ultime due. Anche il kernel le rifiutava con EINVAL, con un TODO relativo a CAP_SYS_NICE. SurfaceFlinger selezionava REALTIME e falliva in vkCreateDevice con VK_ERROR_NOT_PERMITTED, provocando il riavvio del servizio. La sola disponibilità di AHardwareBuffer o di due code non risolveva questo contratto incoerente.

## Implementazione

`DRM_ASAHI_FEATURE_PRIVILEGED_PRIORITY`, bit 1 dei parametri Asahi, è **un’estensione locale dell’ABI ai commit fissati**. Prima di portarla su altre versioni occorre riconciliare l’assegnazione del bit con l’upstream.

Il kernel imposta il bit in GET_PARAMS solo quando il chiamante è autorizzato tramite `capable(CAP_SYS_NICE)`, nel namespace utente iniziale e secondo la policy LSM. È una fotografia dell’autorizzazione del chiamante, non un’autorizzazione trasferibile con il file descriptor. QUEUE_CREATE ricontrolla le credenziali correnti per ogni richiesta HIGH/REALTIME e restituisce EACCES se il permesso manca. Valori fuori dall’intervallo restano EINVAL.

Mesa espone HIGH/REALTIME solo sul percorso DRM diretto quando il kernel restituisce quel bit. Kernel precedenti e chiamanti senza il permesso vedono LOW/MEDIUM. Il trasporto virtio resta su LOW/MEDIUM finché non esiste un contratto di autorizzazione verificato per quel trasporto. Il debug single-queue rifiuta il riuso di una coda con priorità diversa.

Le richieste vengono inoltrate alla creazione della vera coda; EACCES/EPERM diventano VK_ERROR_NOT_PERMITTED. Gli altri errori di creazione restano errori. Non viene sostituita una priorità richiesta con una più bassa per ottenere un successo.

| Vulkan | Valore DRM | Classe firmware AGX |
| --- | --- | --- |
| LOW | 0 | 3 |
| MEDIUM | 1 | 2 |
| HIGH | 2 | 1 |
| REALTIME | 3 | 0 |

Queste sono classi di scheduling. Il nome REALTIME non garantisce scadenze temporali rigide e non completa la preemption compute che l’upstream lascia disabilitata in alcuni percorsi.

## Codice e dipendenze

- Kernel: `sources/linux-asahi/drivers/gpu/drm/asahi/file.rs` e relativo header UAPI.
- Mesa: `sources/mesa/src/asahi/vulkan/hk_queue.c`, `hk_physical_device.c`, helper `agx_device.c/.h` e header UAPI coordinato.
- Test: `scripts/asahi_priority_permissions_probe.c`, `scripts/vulkan_priority_probe.c`, `scripts/vulkan_android_interop_probe.c`.

SurfaceFlinger possedeva già CAP_SYS_NICE nella sessione osservata. Non sono necessari cambiamenti dei privilegi delle app, domini permissive o modifiche di m1n1 per implementare questa funzione.

## Verifiche e stato hardware

La coppia kernel25/Mesa è stata compilata. La policy della priorità, i nuovi header e il driver sono presenti negli artefatti registrati in `tests/results/local-2026-10-17.json`. Il kernel ha letto tutti i file del vendor compresso in VM.

Il controllo negativo sul M1 con il kernel precedente ha ottenuto code LOW/MEDIUM reali e EINVAL per HIGH/REALTIME. Il probe Vulkan ha riprodotto la pubblicizzazione di quattro priorità e il rifiuto delle due superiori. Gli estratti pubblici contengono solo le righe dei probe, senza capture UART integrali.

**La nuova implementazione non è stata caricata sull’M1.** Il proprietario ha interrotto le prove hardware per usare il dispositivo. Restano da verificare: rifiuto EACCES del kernel nuovo per un client non autorizzato; creazione delle classi elevate da un owner autorizzato; esecuzione Vulkan di SurfaceFlinger; progresso e stabilità con più client; revoca della capability dopo la discovery. Nessuna di queste prove viene dedotta dalla sola compilazione.
