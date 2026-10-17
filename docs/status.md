# Stato al 17 ottobre 2026

## Risultati già osservati sul M1

Android ha completato il boot con SELinux Enforcing. Wi-Fi si è collegato a una rete; l’utente ha confermato l’ascolto con cuffie Bluetooth e, dopo le correzioni del primario ALSA, con gli altoparlanti interni. La Touch Bar ha funzionato ed è stata corretta la deformazione delle icone.

Il driver Vulkan precedente ha superato i test di import/export AHardwareBuffer, quattro frame di swapchain e otto sequenze di dipendenza su due code native. Impostazioni ha usato Skia Vulkan con 97 frame renderizzati, con conferma visiva dell’utente. Queste prove riguardano quel driver, non la nuova build delle priorità.

L’attivazione di Vulkan per SurfaceFlinger ha rivelato il rifiuto di una priorità che il driver dichiarava disponibile. Il compositore è stato temporaneamente riportato a OpenGL nella sessione di debug. La correzione ora presente nei sorgenti modifica sia il kernel sia Mesa.

## Nuova build verificata localmente

Kernel25 e Honeykrisp con priorità autorizzate sono compilati. Gli header UAPI del kernel e di Mesa coincidono; la patch GPU è stata confrontata con i sorgenti, e le patch complete vengono verificate rispetto ai commit di base.

La nuova immagine vendor contiene 3.385 elementi, di cui 2.801 file regolari confrontati per hash. Proprietari, permessi, tipi, link e attributi di sicurezza sono verificati. Il kernel25 ha letto e controllato tutti i file del filesystem compresso in VM. Configurazione e DTB mantengono le identità del profilo precedente. Le modifiche del vendor rispetto alla versione18 riguardano solo la libreria Vulkan e il manifest dell’integrazione.

**Le prove hardware sono sospese su richiesta dell’utente. La nuova coppia kernel25/Mesa non è installata né qualificata sul M1.** La sessione già in uso non è stata riavviata per provarla.

## Parti ancora aperte

- Validazione delle priorità sul kernel nuovo, compresi permessi, revoca e lavoro GPU sotto concorrenza.
- Avvio e stabilità di SurfaceFlinger e delle app con la nuova coppia.
- Adattatore Android Codec2 per il decoder AVD stateless; l’inventario corrente seleziona codec software.
- Backend hardware di encoding.
- Qualifica estesa del DSP/volume speaker e della durata termica, del cursore Android di illuminazione per tastiera e delle altre funzioni non provate.
- Avvio diretto senza hypervisor di debug e build completa riproducibile della distribuzione.

I report selezionati pubblicano gli hash e la portata dei test, senza includere log privati o pretendere conformità Vulkan CTS o certificazione Android.
