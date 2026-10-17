# Modifiche per l’avvio Android sul J293

## Boot e storage

Il kernel e l’initramfs vengono trasferiti in RAM attraverso m1n1. Android usa le proprie partizioni sul NVMe interno. Il profilo Linux conserva i driver Apple necessari e rimuove componenti di piattaforme non pertinenti; il kernel usa pagine da 16 KiB.

L’immagine di partenza aveva partizioni GPT prive dei nomi richiesti dal percorso Android. Il port assegna i nomi `super`, `metadata` e `userdata` nel censimento Linux, mediante corrispondenze esplicite con le partizioni attese. Non riscrive i nomi GPT. Nella copia pubblicata gli UUID sono esempi e vanno configurati per la macchina interessata.

Il bootstrap trasporta il firmware una sola volta e conserva il manifest dei payload originali. La procedura di aggiornamento modifica solo le aree previste di `super`: verifica la versione attiva, protegge gli extent precedenti, richiede una copia completa di ripristino per un extent inattivo riutilizzato e verifica payload e copie liblp prima di avviare Android.

La compatibilità Android include il percorso memfd/ashmem richiesto da questo userspace. Gli adattamenti per la compilazione sul Mac sono separabili dalle modifiche necessarie al funzionamento sul M1.

## Grafica e sincronizzazione

Asahi/DRM controlla la GPU fisica; DCP gestisce il display principale e ADP il display della Touch Bar. minigbm e drm-hwcomposer vengono adattati al censimento effettivo, ai buffer e ai fence. Le correzioni DRM CRTC della durata e della race dei fence sono conservate con la loro provenienza upstream.

Honeykrisp riceve l’integrazione Android native-buffer/AHardwareBuffer e il percorso acquire/release. Gli import usano layout e stride effettivi; i fence sono eventi reali. Il supporto a due code native usa worker distinti e protegge gli heap condivisi attraverso il completamento GPU osservato. Le nuove priorità sono una modifica ulteriore descritta nella pagina dedicata.

## HAL, input e audio

Il prodotto Android di partenza contieneva servizi e percorsi Qualcomm non corrispondenti all’hardware Apple. Gli script di staging selezionano i componenti pertinenti e installano le implementazioni locali; i permessi SELinux sono mirati e le prove sul dispositivo mantengono Enforcing.

Wi-Fi usa il backend Linux e l’interfaccia HAL del prodotto. Bluetooth collega il controller Linux e la factory audio già presente nell’immagine. Il servizio Lights espone le interfacce AOSP corrispondenti alla matrice effettiva; gli errori del pannello principale, della tastiera e della Touch Bar rimangono indipendenti.

La Touch Bar usa ADP, buffer KMS e completion dei page flip, con rotazione e pitch corretti. Il daemon osserva il sensore effettivo e produce eventi uinput, gestendo slot multitouch, rilasci, cambi di layout e perdita di sincronizzazione.

Il servizio audio primario espone una porta Android stereo PCM16 a 48 kHz e usa il PCM AppleJ293 S32_LE a quattro canali. Mantiene FIR e mapping fisico, limite digitale e interlock. speakersafetyd conserva modello termico e monitoraggio V/I. Le correzioni dell’indirizzo AIDL, di XRUN e della sequenza pausa/flush/standby hanno preceduto la conferma acustica degli speaker.

## Video e limiti del debug

Il linker del firmware AVD open source è stato corretto affinché i vettori Cortex-M3 inizino a zero. Il driver è presente, ma Android usa ancora componenti software perché il percorso Codec2 per V4L2 Request stateless non è integrato. Il servizio hardware di encoding non è implementato.

Per i log, le prove hanno impiegato la modalità hypervisor m1n1 e la sua UART virtuale su USB. L’output iniziale veniva acquisito prima della disponibilità di `/data`; in seguito il logcat completo passava su file con sovrapposizione temporale e recupero verificato tramite SHA-256. I log privati e il coordinatore della sessione fisica sono esclusi dal rilascio.
