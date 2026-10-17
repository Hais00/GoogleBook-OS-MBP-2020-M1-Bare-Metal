> Historical engineering notes. The current status is in ../../README.md and ../../docs/status.md; earlier candidate/pending sections describe their original phase.

# Touch Bar: audit del difetto grafico

L’utente conferma che la Touch Bar risponde ai comandi, ma le etichette rimangono deformate anche da ferme. La prova corrente è `trial-native-input-kernel22-c`, kernel 22, vendor generation 9 / input R3.

La classe Font estratta dal sorgente di produzione e la stessa funzione rowPixel generano un’immagine leggibile sia sul computer sia sull’M1. I due file PGM coincidono byte per byte (SHA256 e5413ed1678168e97f43be2f51e062d60487cc3d2ebb95e670e3d7cf9674e303). Il trasferimento dalla console è stato verificato con SHA256. Il renderer host passa ASan/UBSan.

La prova usa memoria CPU, dimensioni 60×2008, pitch assunto di 240 byte e altezza allocata di 2048 righe. Non legge il framebuffer attivo e non verifica pitch effettivo, orientamento fisico o vincoli di allineamento ADP. Non qualifica quindi la resa del pannello. Il codice del driver programma direttamente il DMA address e il pitch del framebuffer; la presenza degli helper shadow non dimostra una copia mancante.

Rimane da classificare la deformazione fisica tramite una foto e verificare i parametri effettivi del buffer. Non è stata applicata una correzione ipotetica, modificata una partizione o effettuato un riavvio. I comandi touch e le richieste PWM osservate restano funzionanti. Il logger completo PID 501 continua nel file della sessione; la UART conserva kernel e crash.

Ricevuta: `.agent-work/touchbar-render-audit/runtime-result.json`. Immagine ottenuta dal test CPU sull’M1: `.agent-work/touchbar-render-audit/actual-m1-cpu.png`.

## Foto e prova di allineamento

La foto IMG_1441.jpg conferma tratti delle lettere spezzati e ripetuti, con i riquadri ancora distinguibili. Una simulazione in cui il buffer ha pitch 240 byte ma viene letto con passo 192 byte produce lo stesso tipo di distorsione e dilatazione orizzontale. È un indizio, non una lettura dei registri ADP. Il tentativo di interrogare i metadati KMS dalla shell ha ricevuto errno 13 all’apertura della scheda ADP; non sono state ampliate le autorizzazioni.

La candidata `kernel-adp-scanout-pitch.patch` usa l’helper DRM `drm_mode_size_dumb()` con allineamento di riga 64 byte, preserva il precedente arrotondamento dell’altezza a 64 righe e aggiunge una misura di allocazione nel log. Per 60×2008 XRGB8888 il pitch diventa 256 byte. La gestione overflow e la dimensione page aligned sono affidate all’helper kernel; l’arrotondamento altezza è controllato prima. La prova con lo stesso renderer a pitch 256 passa ASan/UBSan e genera esattamente l’immagine logica precedente.

Il kernel 23 è una prova RAM con configurazione identica al 22. Vendor generation 9 e il programma Touch Bar rimangono quelli installati. L’efficacia sul pannello richiede ancora la prova fisica successiva al boot.

## Esito fisico

Il kernel 23 registra sul M1 `scanout allocation 60x2048 pitch=256 bytes size=524288`. Android completa il boot, il servizio Touch Bar è attivo e l’utente conferma «ha risolto». La correzione dell’allocazione ADP risolve quindi il difetto osservato. Vendor generation 9 è rimasto invariato. I log completi della precedente sessione kernel22-c sono stati trasferiti e verificati prima del riavvio da Android.
