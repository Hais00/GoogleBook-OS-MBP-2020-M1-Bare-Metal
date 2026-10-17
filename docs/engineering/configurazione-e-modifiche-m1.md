> Nota storica delle prime fasi fino al kernel12. Per lo stato attuale vedere [README](../../README.md) e [stato](../status.md). Percorsi e identificativi personali sono sostituiti con esempi.

# GoogleBook OS su Apple M1: configurazione e modifiche

Revisione: kernel **#12**, 16 ottobre 2026. MacBookPro17,1 / J293 / SoC T8103.
Directory progetto: `/opt/googlebook/project`.

Questo documento descrive il payload diagnostico preparato per la prova fisica
richiesta dall'utente. L'esito effettivo della scrittura, gli hash riletti e il
percorso del backup sono in `.work/installed-manifest.json`. Non equivale a una
certificazione del boot completo: Android non ha ancora completato un avvio
stabile in QEMU e la grafica AGX/DCP non è stata validata sul Mac.

## 1. Catena di avvio e confini dell'installazione

Catena: boot Apple → m1n1 → U-Boot → GRUB o extlinux → kernel/initrd Android.
Lo stub Apple, m1n1 stage 1, la ESP abbinata a UEFI su `disk0s4` e il relativo
stage 2 non vengono aggiornati da questa installazione.

| Destinazione | UUID GPT | Dimensione in byte | Azione |
|---|---|---:|---|
| `disk0s7`, EFI-GOS | `00000000-0000-4000-8000-000000000002` | 999997440 | Aggiornamento file boot e documentazione |
| `disk0s8`, super | `00000000-0000-4000-8000-000000000001` | 8899264512 | Sostituzione immagini Android, con conservazione dello stato logico esistente |
| `disk0s9`, metadata | `00000000-0000-4000-8000-000000000004` | 63963136 | Nessuna scrittura dell'installer |
| `disk0s10`, userdata | `00000000-0000-4000-8000-000000000005` | 321589870592 | Nessuna scrittura/formattazione dell'installer |

Nessun cambiamento alla GPT, agli altri sistemi, alla recovery o allo spazio
libero esterno all'allocazione Android. Il successivo avvio Android può scrivere
normalmente nei propri filesystem metadata e userdata.

La FAT di EFI-GOS ha UUID `0D87-0D88` e settori da 4096 byte. GRUB usa questo
UUID, evitando dipendenze dai nomi `nvme0/1/2`. Il bridge
`EFI/debian/grub.cfg` rinvia alla configurazione in `boot/grub`.
La versione 2.06 visualizzata da GRUB è quella del bootloader.

## 2. Kernel e ambiente di compilazione

- Asahi Linux `7.1.13-googlebook-m1+`, build #12.
- Commit base: `94fb23346d522edf53722357c426a3e58030beea`.
- Sorgenti: `/opt/googlebook/build/linux-asahi`.
- Configurazione completa: `scripts/kernel-googlebook.config`.
- Copia della configurazione effettiva: `.work/kernel-native-usb-input-checkpoint/config`.
- Differenza completa rispetto al #6 precedentemente installato:
  `.work/kernel6-to-kernel12-config.diff`.
- Patch della compilazione macOS e del riconoscimento delle partizioni:
  `scripts/kernel-macos-m1.patch`; header host in `scripts/kernel-host-include`.
- Build: `scripts/build_kernel.sh`, con `olddefconfig` prima di `Image dtbs`.
- Toolchain: LLVM 19, Rust 1.85.0, bindgen 0.73.2, GNU make/sed;
  Android NDK r28 per i componenti userspace ARM64, API 34.
- ELF userspace costruiti con allineamento compatibile con pagine da 16 KiB.

Il volume virtuale `/opt/googlebook/build` proviene da `.work/GOSBuild.sparseimage`.
Il supporto ownership è stato abilitato solo su questo volume immagine per
preservare UID/GID Android durante la ricostruzione EROFS di system.

### Configurazione già presente nel kernel #6

Pagine ARM64 da 16 KiB; Binder e BinderFS; SELinux, `SECURITY_NETWORK` e SELinux
in `CONFIG_LSM`; cpuset v1 e `PROC_PID_CPUSET`; NVMe; EROFS/ext4 con etichette
di sicurezza; driver Asahi AGX e Apple DCP integrati; console Samsung/earlycon.
Il riconoscimento dei nomi super/metadata/userdata per gli UUID sopra indicati
è limitato a quelle partizioni, senza rinominare la GPT fisica.

### Aggiunte dal #6 al #12

| Area | Principali opzioni e scopo |
|---|---|
| Quota ext4 | `QFMT_V2=y`, `QUOTA_TREE=y`: soddisfare il mount quota richiesto da vold |
| Filesystem | `FS_ENCRYPTION=y`, `FS_VERITY=y`, `UNICODE=y` e algoritmi associati |
| ART | `USERFAULTFD=y` e relativo supporto architetturale |
| Rete Android | iptables legacy IPv4/IPv6, netfilter/conntrack/NAT, policy routing, filtri, tunnel/IPsec, BPF classifier/action, VETH |
| Scheduling | `UCLAMP_TASK=y`, `UCLAMP_TASK_GROUP=y`, `PM_WAKELOCKS=y` |
| VM/IPC | VSOCKETS, VIRTIO_VSOCKETS, VHOST_VSOCK, TAP/MACVTAP e VHOST_NET integrati |
| Input/USB Apple | APPLE_TUNABLE, HID_MULTITOUCH, PHY_APPLE_ATC, TYPEC_TPS6598X e TYPEC_DP_ALTMODE passano da moduli a integrati |
| QEMU | DRM_VIRTIO_GPU, virtio DMA shared buffer e SND_VIRTIO integrati |
| ALSA | SOUND, SND, SND_PCM e SND_TIMER integrati; nessun audio Apple abilitato |
| Accessi non necessari | DEVMEM e MTD_SPI_NOR disabilitati |

I driver audio Apple MCA/codec non vengono attivati da questo lavoro. La
presenza di ALSA/virtio sound serve alle prove e non abilita gli altoparlanti.
Non è stata applicata una nuova patch al driver DCP/AGX per cambiare i formati.

## 3. Immagini Android e mount

Il sistema deriva dall'immagine recovery originale
`android-desktop_signed_recovery_image.bin`. Si usa il vero `system_a`:
`system_b`/system-other non è una root Android avviabile equivalente.

`scripts/build_fixed_super.py` sostituisce system_a, vendor_a e system_ext_a,
preserva product_a, aggiorna e verifica tutte le copie dei metadati liblp.
Le nuove regioni sono allocate solo all'interno della dimensione esistente di
super, con controlli su checksum, limiti e sovrapposizioni.

Sono aggiunte regioni logiche scrivibili: `misc` 4 MiB,
`desktop_security_storage` 32 MiB e `desktop_security_persist` 16 MiB.
L'installer conserva i loro contenuti se già presenti. Nell'installazione
fisica #6 letta prima dell'aggiornamento queste tre regioni non erano presenti.

Fstab in initrd e vendor:

```text
system_a /system erofs ro wait,logical,first_stage_mount
vendor_a /vendor erofs ro wait,logical,first_stage_mount
product_a /product erofs ro wait,logical,first_stage_mount
system_ext_a /system_ext erofs ro wait,logical,first_stage_mount
/dev/block/by-name/metadata /metadata ext4 noatime,nosuid,nodev wait,first_stage_mount,formattable
/dev/block/by-name/userdata /data ext4 noatime,nosuid,nodev wait,check,formattable,quota,latemount
/dev/block/mapper/misc /misc emmc defaults defaults
```

`formattable` è un'opzione di Android init, non un'azione dell'installer.
L'installer non formatta i filesystem. La configurazione attuale non richiede
FBE: `/data` è non cifrata. Il supporto fscrypt nel kernel non cambia questo
stato né converte i dati esistenti.

## 4. Grafica Apple e differenze con QEMU

Profilo installabile: `prepare_m1_install.py --profile m1`, senza `--trace-drm`.

- Mesa 25.3.6, Vulkan Honeykrisp/Asahi: `ro.hardware.vulkan=asahi`.
- ANGLE per EGL/GLES: `ro.hardware.egl=angle`.
- minigbm/CrOS gralloc: `ro.hardware.gralloc=cros`; allocator AIDL v2 e mapper stable-C v5.
- Backend `apple` nell'allocatore: buffer DMA lineari con import/export PRIME;
  il driver DCP allinea il pitch a 64 byte e la dimensione a 16 KiB.
- Il compositore desktop originale usa il backend DRM generico.
  `libm1gate.so` restituisce backend SDM non disponibile tramite
  `sdm::GetSDMInterfaceFactory()`; dipendenza ELF esplicita, senza LD_PRELOAD.
- Compressione/UBWC e overlay disattivati nel profilo di avvio.
- Composizione SDR/WCG richiesta in RGBA8888 (`pixel_format=1`).
- Il tracciamento sostitutivo `gosModeAddFB2*` è solo diagnostico QEMU e non
  è attivato nell'eseguibile HWC destinato al Mac.

| Android | DRM FOURCC su ARM little-endian | Driver Apple DCP |
|---|---|---|
| RGBA8888 | ABGR8888 | Accettato, tradotto in DCP_FORMAT_RGBA |
| BGRA8888 | ARGB8888 | Accettato, tradotto in DCP_FORMAT_BGRA |
| RGBX8888 | XBGR8888 | Accettato come superficie opaca |

Riferimenti nel codice: `minigbm/cros_gralloc/cros_gralloc_helpers.cc`,
`minigbm/dumb_driver.c`, kernel `drivers/gpu/drm/apple/{plane.c,apple_drv.c}`.
Le superfici devono essere lineari, con pitch multiplo di 64 byte. Le
operazioni sulle plane restano soggette ai vincoli geometrici del driver.

Nel log hardware #6 sotto hypervisor si inizializza soltanto simpledrm sul
framebuffer di boot (`bd5d5c000.framebuffer`). Non compare la conferma di
attivazione di Apple DCP/AGX. simpledrm è un percorso distinto: espone il
formato framebuffer nativo e XRGB8888 emulato; l'allocatore attuale non ha un
backend simpledrm. La prima prova fisica deve verificare questa distinzione.

Il profilo `virt` usa SwiftShader (`vulkan.pastel.so`) e non prova la GPU Apple.
SwiftShader è costruito dal commit `cddb5c91b23ff70a1f607ea31610aa0d7f4b5ad5`;
`scripts/swiftshader-android.patch` corregge il percorso Android della memoria
JIT, evitando l'esecuzione da memfd negata dalla policy. Il caricamento HAL,
l'allocazione e un lavoro Vulkan CPU sono stati eseguiti in Android/QEMU.
L'ultima prova grafica QEMU resta bloccata: virtio rifiuta ABGR e la proprietà
BGRA da sola non modifica tutti i buffer richiesti dal compositore. Non è
stata applicata la successivamente ipotizzata patch virtio al kernel.

## 5. Modifiche a vendor, init e SELinux

Preparazione: `scripts/prepare_m1_install.py`.

- Nuovi XML VINTF e RC init etichettati `vendor_configs_file`, leggibili dai servizi corretti.
- Librerie gralloc/mapper/GBM/Vulkan con etichetta `same_process_hal_file`.
- Eseguibili allocator e audio con le rispettive etichette HAL originali.
- File disabilitati spostati fuori dalle directory init/VINTF: il suffisso
  `.disabled` da solo non ne impediva il parsing.
- Permessi per nodi DRM e per le nuove regioni di sicurezza logiche.
- Firmware macchina nell'initrd e in vendor/firmware; conservati i tipi SELinux.
- Azione Google di firmware roll-forward esclusa da questo profilo Apple.
- Rimossa la policy precompilata vendor quando non corrisponde alla CIL modificata,
  così init compila le effettive policy anziché usare una cache obsoleta.

SELinux resta enforcing. La CIL mantiene la regola `(allow bootanim self (process (execmem)))` per il
JIT del renderer software. Dopo la cattura USB sono aggiunte le etichette
genfscon dei soli uevent Apple e la lettura sysfs_gpu per la shell diagnostica
(vedere sezione 13); i client grafici usano i permessi GPU già presenti.
Le precedenti opzioni sperimentali di ptrace/debug Trusty non sono abilitate.

## 6. BootControl, sicurezza e audio

- `scripts/bootcontrol_m1.cpp`: servizio a singolo slot con record standard
  bootloader_control nella regione logica misc. Non apre la GPT del disco Mac.
- `ro.build.ab_update=false` e proprietà Virtual A/B/snapshot disattivate.
- StrongBox GSC/Titan escluso dallo scan APEX; servizio gscd disabilitato e
  Secretkeeper VM non pubblicizzato sul Mac privo di quel dispositivo.
- `scripts/keymint_software.cpp`: utilizza l'implementazione AOSP presente
  nell'immagine (`libkeymint_fake_latest.so`) richiedendo realmente
  `SecurityLevel::SOFTWARE`; controlla il livello restituito. Espone KeyMint,
  secure clock, shared secret e RKP tramite le implementazioni software.
  Non simula TEE/StrongBox/SEP o una certificazione hardware.
- Header keymaster: commit `cabf20e824b15ea48a95f770ada21777c1e32d8e`.
  Build e hash: `.work/software-keymint-build.json`.
- Registrazione in Keystore2, shared-secret e operazioni odsign osservate in QEMU.
- Trusty non protetto configurato con una CPU, CID 200 e servizi RPC/VSOCK.
  Gatekeeper/PIN e l'intero percorso di storage protetto non sono validati.
- RPMB mock usa le regioni logiche sopra elencate, senza vantare protezione hardware.

Audio: `vendor.audio.dras.default_nothing=true` seleziona il modulo vuoto fornito
dall'immagine. Una copia del DRAS originale carica `libgosagmservice.so` invece
di `libagmipcservice.so`; il nuovo adattatore restituisce `-ENODEV`, evitando
il lungo tentativo Qualcomm AGM. Il servizio conserva il dominio HAL audio.
L'avvio del Nothing HAL senza scheda ALSA è stato osservato in QEMU.
Non c'è output audio né pilotaggio degli altoparlanti Apple.

## 7. Modifica limitata al framework OEM

`scripts/prepare_system_m1.py` modifica in `desktop-services.jar` solo i corpi
dei metodi pubblici `onStart()` e `onBootPhase(int)` di
`com.android.server.desktop.repairmode.DesktopRepairModeService`.

Il watchdog aveva mostrato il thread principale fermo su dati di fabbricazione
GSC nella fase 520. Quel servizio può anche gestire/rimuovere una partizione
di riparazione OEM non pertinente alla GPT Mac. I due hook vengono resi inerti;
il resto del DEX e gli offset ZIP sono mantenuti, con checksum ricalcolati.
Eliminati soltanto i relativi odex/vdex e metadati fs-verity divenuti obsoleti.

system è ricostruito dall'estrazione originale con UID/GID, mode, capability
e xattr SELinux conservati. EROFS ha superato il controllo integrale.
Prova dettagliata: `.work/system-m1-repair-policy.json`. La verifica runtime
oltre quella fase resta necessaria dopo aver risolto l'inizializzazione display.

## 8. Logging e prova fisica

Gli argomenti completi sono riportati in fondo e definiti una sola volta in
`scripts/boot_config.py`. Comprendono UART, earlycon, buffer kernel da 4 MiB,
`printk.devkmsg=on`, `panic=0` ed `enforcing=1`.
Lo stato Verified Boot è dichiarato orange/unlocked/verity disabled: non viene
presentato il payload modificato come immagine verificata e bloccata.

`androidboot.googlebook.debug=1` abilita una console seriale di sviluppo UID
2000, dominio shell, con accesso ai log ma senza shell root. Per disattivarla,
rimuovere questo argomento e rigenerare le configurazioni prima dell'installazione.
logd richiede 16 MiB tramite ro.logd.size e persist.logd.size dopo il caricamento
delle proprietà persistenti; il valore effettivo resta da controllare sul Mac.

Il vecchio logger `/metadata/googlebook-logs` falliva con la policy release ed
è stato rimosso: non va considerato una fonte affidabile di log.

Avvio nativo: nelle opzioni Apple scegliere UEFI, poi la voce GoogleBook OS.
Non sostituire manualmente il device tree dinamico fornito da m1n1/U-Boot con
un DTB statico: mancherebbero informazioni firmware e riserve memoria runtime.

Per la cattura sul secondo Mac usare il nuovo `dist/GoogleBook-USB-Debug.zip`:

```sh
python3 capture_uart.py /dev/cu.usbmodemP_03 --commands-file android_hardware_watch.sh
```

La porta è indicativa: identificare la UART secondaria, separata dal proxy
primario. Quando compare GOS_CONSOLE_READY, lo script invia i comandi per
logcat e campionamento dello stato del boot. Il file raw resta sul Mac ricevente.
Prerequisiti: Python con pyserial; per m1n1 anche construct e il suo ambiente.
Le modifiche a questa automazione non sono ancora provate sulla UART fisica.

Se si usa il wrapper incluso per un guest m1n1:

```sh
python3 boot_usb_debug.py /percorso/al/proprio/m1n1 --device /dev/cu.usbmodemP_01
```

Usa un proprio m1n1 già compilato e compatibile, caricato in RAM. Non modifica
lo stage 2 su disco. Il test sotto hypervisor può differire dall'avvio nativo.
In alternativa il flusso già usato con U-Boot guest può leggere i nuovi file
da NVMe partizione 7. Non riutilizzare sulla macchina ricevente il vecchio Image #6.

Controlli da ricercare nella prossima cattura:

1. Banner kernel #12 e completamento di apexd-bootstrap.
2. Driver dei nodi `/dev/dri`: Apple DCP/AGX oppure solo simpledrm.
3. Registrazione allocator/mapper/HWC senza dinieghi SELinux/linker.
4. Avanzamento di SystemServer oltre le fasi 100 e 520 senza watchdog.
5. `sys.boot_completed=1`, processi system_server/SurfaceFlinger stabili e frame visibile.
6. Renderer effettivo e funzionamento input; solo dopo, verifica dell'accelerazione GPU.

## 9. Ricostruzione, installazione e backup

Percorsi relativi nei comandi riferiti alla directory progetto. I componenti
compilati sono conservati in `/opt/googlebook/build/graphics-out`.

```sh
python3 scripts/build_graphics.py core
python3 scripts/build_graphics.py common
python3 scripts/build_graphics.py mapper
python3 scripts/build_graphics.py legacy
python3 scripts/build_graphics.py allocator
python3 scripts/build_graphics.py backend_gate
python3 scripts/build_graphics.py bootcontrol
python3 scripts/build_graphics.py software-keymint
python3 scripts/build_graphics.py audio-no-agm
python3 scripts/build_graphics.py label-probe
python3 scripts/build_graphics.py native-vkprobe
python3 scripts/prepare_system_ext_m1.py --software-keymint --one-cpu --software-vulkan
sudo -n python3 scripts/prepare_system_m1.py
python3 scripts/prepare_m1_install.py --profile m1
mkfs.erofs --quiet -b4096 -zlz4hc,12 --workers=4 --all-root extracted_partitions/vendor_m1_fixed.img vendor_work
mkfs.erofs --quiet -b4096 -zlz4hc,12 --workers=4 --all-root extracted_partitions/system_ext_m1_fixed.img /opt/googlebook/build/system-ext-work
python3 scripts/validate_vendor_image.py extracted_partitions/vendor_m1_fixed.img --profile m1
python3 scripts/build_fixed_super.py
```

Per system non usare --all-root: lo script dedicato conserva i reali UID/GID
Android. I file Image/DTB vanno copiati dal checkpoint del kernel effettivamente
testato e il relativo risultato smoke aggiornato prima dell'installer.

L'installer mantiene per impostazione predefinita il requisito del boot completo
QEMU. Per questa prova hardware richiesta esplicitamente dall'utente si usa:

```sh
sudo -n diskutil mount disk0s7
sudo -n python3 scripts/install_fixed_m1.py --hardware-bringup
```

La modalità viene registrata come diagnostica, senza inventare un esito positivo
QEMU. Restano obbligatori controlli UUID/dimensioni/GPT, profilo Apple senza
tracciamento, etichette vendor, integrità delle sorgenti e smoke test kernel.

Prima della prima scrittura, l'installer conserva super completo, file EFI
correnti, GPT primaria/secondaria e vecchio manifest in una directory privata
`.work/backup-before-hardware-*`. L'immagine sparse di super mantiene la
dimensione logica completa. Il backup viene riletto e confrontato con SHA-256.
Le regioni logiche scrivibili eventualmente esistenti sono salvate e conservate
anche da `scripts/android_lp_state.py`. Non condividere questi backup privati.

L'installer scrive soltanto super e i file elencati di EFI-GOS; rilegge l'intero
super e ogni file EFI per verificarne l'hash, poi ricontrolla entrambe le GPT.
L'ultimo manifest contiene il percorso concreto del backup e gli hash fisici.
Per ripristinare usare quel backup sulle stesse partizioni identificate per UUID,
non un'immagine dell'intero disco. `dist/googlebook_os_m1.img` è obsoleta e non
deve essere usata per questa installazione.

## 10. Evidenze disponibili e limiti

- `.work/selinux-smoke-results-kernel12.json`: mount SELinux enforcing, Binder,
  cpuset v1 con assegnazione task, burst kmsg, quota ext4 e funzionalità filesystem.
- La prova di caricamento della policy Android originale è stata eseguita in
  una VM separata permissive; non dimostra ogni accesso della policy runtime.
- Avvii Android QEMU con SELinux enforcing e le nuove immagini hanno raggiunto
  diversi servizi, KeyMint software e rendering CPU, ma non il desktop stabile.
- `scripts/test_android_lp_state.py`: conservazione dello stato, migrazione da
  layout precedente, permessi backup e rifiuto di metadati corrotti.
- `.work/vendor-vintf-label-validation.json`: estrazione EROFS, etichette reali,
  profilo m1, composizione RGBA e assenza di import HWC diagnostici.
- `M1-Linux-kernel-6-logs-2026-10-16` nella home: precedente cattura hardware.

Il binding DCP/AGX è stato osservato nella successiva prova USB (sezione 13).
Restano aperti: esecuzione GPU, importazione e presentazione dei buffer, boot
completo, accelerazione, input completo, credenziali/TEE e audio.
Questa è una build di sviluppo, con KeyMint software, dati non cifrati e
console diagnostica abilitata. Il prossimo avvio raccoglie evidenze hardware;
non viene dichiarato già funzionante.

## 11. Identità esatta del payload

La sezione seguente viene compilata dai file preparati per questa revisione.

### Riga di comando kernel

```text
earlycon console=tty0 console=ttySAC0,115200n8 ignore_loglevel loglevel=8 log_buf_len=4M printk.devkmsg=on panic=0 enforcing=1 root=/dev/ram0 init=/init androidboot.hardware=android-desktop androidboot.slot_suffix=_a androidboot.super_partition=super androidboot.boot_part_uuid=00000000-0000-4000-8000-000000000002 androidboot.verifiedbootstate=orange androidboot.vbmeta.device_state=unlocked androidboot.flash.locked=0 androidboot.veritymode=disabled androidboot.force_normal_boot=1 androidboot.googlebook.debug=1 androidboot.serialconsole=1 androidboot.console=console clk_ignore_unused pd_ignore_unused
```

### SHA-256 dei file boot

| File | SHA-256 |
|---|---|
| `Image` | `dbe1df9b603be472c2ebb7b65cab2a34a132336cb017c30d2842ce8b70ed3503` |
| `initrd.img` | `390f328d57e2b62036867005da29d455b60302646e143a39dbefc9f2b5934197` |
| `t8103-j293.dtb` | `ea32173df3b0f782bf610f38fb390f90a777c16d4a4b2822c58b924bc6088328` |

### Immagini logiche del template super

| Partizione | Byte | Offset in super | SHA-256 template |
|---|---:|---:|---|
| `system_a` | 1105584128 | 1048576 | `ff1461e6f30fdfafef274f3b4b1b7faf09ee8edec279321355917090f3edeecc` |
| `vendor_a` | 457269248 | 1107296256 | `fb86109758e96c5da9d8889df7ce15abd416838be44342c72a4a2680cd88a1b1` |
| `system_ext_a` | 202010624 | 6814695424 | `65ea181bf2f0851993f1a0c33d34b6d8c00c6c95d81503a331a237b8c5834814` |
| `misc` | 4194304 | 7017070592 | `cd287c86034d9e78c5328ce074944f50dacae623ff49e56e9f5ab446fe6cfd84` |
| `desktop_security_storage` | 33554432 | 7021264896 | `83ee47245398adee79bd9c0a8bc57b821e92aba10f5f9ade8a5d1fae4d8c4302` |
| `desktop_security_persist` | 16777216 | 7054819328 | `080acf35a507ac9849cfcba47dc2ad83e01b75663a516279c8b9d243b719643e` |

Gli hash dello stato scrivibile possono cambiare al boot.

## 12. Cattura hardware #12 e aggiornamento console

Cattura: `/opt/googlebook/host/M1-Linux-kernel-12-logs-2026-10-16/`.
Analisi strutturata: `.work/kernel12-hardware-diagnosis.json`.

- Il kernel corretto #12 e apexd-bootstrap sono partiti. Nei 157 secondi catturati
  non compare panic kernel o riavvio automatico.
- SurfaceFlinger termina con SIGABRT 26 volte; l'allocatore esce con stato 1
  27 volte. L'intervallo mediano fra i crash grafici è circa 5 secondi.
- Non è disponibile il messaggio di abort interno: logcat non ha raggiunto la UART.
- La GPU espone nel modalias soltanto apple,agx-g13g; il driver Asahi di questo
  kernel richiede apple,agx-t8103. Il DTB preparato contiene entrambi i compatible,
  oltre a apple,dcp e apple,display-subsystem.
- Il vecchio guest m1n1/U-Boot usa dunque un DT diverso da quello preparato:
  caricare Image #12 da NVMe non sostituisce il DT passato dal bootloader.
  Nel log compare simpledrm, senza attivazione osservata di DCP/AGX.
- L'allocatore presente non ha un backend simpledrm. Questo costituisce un
  ostacolo all'avvio grafico con il solo framebuffer di boot, distinto dai
  dinieghi SELinux su uevent e dalla causa interna degli abort da acquisire.

La console era richiesta a 2,850169 s, prima del completamento coldboot a
2,940660 s. Il servizio viene ora richiesto nella fase init, dopo
wait_for_coldboot_done, come la console Android originale. Questo elimina
una possibile corsa sui nodi dispositivo; l'assenza della console nella cattura
non basta a provare che fosse la sua unica causa. Sono esplicitati
androidboot.serialconsole=1 e androidboot.console=console.

Per la prossima prova usare il nuovo pacchetto USB e boot_usb_debug.py: carica
in RAM kernel e DTB abbinati, lasciando che m1n1 completi i fixup runtime.
Non riusare uboot-hv-cb1024.raw invariato del precedente launch_hv.py.
Non è stato modificato lo stage 2 m1n1 su disco e non è stato forzato un DTB
statico da GRUB. Il funzionamento con il DT corretto richiede una nuova cattura.

Riferimento per ordine di avvio e controllo console:
[Android init Service](https://android.googlesource.com/platform/system/core/+/refs/heads/main/init/service.cpp).

Verifica della correzione console: QEMU ha terminato il coldboot a 8.643586 s
e ha avviato la shell a 10.760373 s. Comandi e UID 2000 confermati.
Risultato: `.work/console-coldboot-validation.json`. Questa verifica non
equivale alla conferma della UART fisica o del boot Android completo.

Verifica della correzione console: QEMU ha terminato il coldboot a 8.643586 s
e ha avviato la shell a 10.760373 s. Comandi e UID 2000 confermati.
Risultato: `.work/console-coldboot-validation.json`. Questa verifica non
equivale alla conferma della UART fisica o del boot Android completo.

## 13. Prova USB con DTB corretto: binding riuscito, etichette DRM da correggere

Cattura: `/opt/googlebook/host/M1-GoogleBook-USB-Debug-logs-2026-10-16/`.
Analisi: `.work/usb-hardware-graphics-diagnosis.json`.

Il kernel #12 è invariato. La prova con il DTB abbinato conferma l'inizializzazione
Asahi (minor 1) e Apple DCP (minor 3), oltre alla console UID2000 e SELinux
enforcing. Questo prova il binding dei driver, non ancora l'esecuzione GPU.

Il logcat ora mostra Vulkan/ANGLE che non inizializza e SurfaceFlinger che
aborta per assenza di EGLConfig. Due ostacoli sono identificati nei dati:

1. `/dev/dri/card3` ha tipo SELinux generico `device`, perché la configurazione
   originale copriva soltanto card0/card1. Il kernel la crea per DCP; l'allocatore
   ne riceve il diniego read/write. Ora i pattern card[0-9]+ e renderD[0-9]+
   assegnano il tipo Android già esistente gpu_device, senza fissare gli indici.
2. L'uevent GPU (inode 7212, confermato dal tentativo della shell su card1)
   resta sysfs generico. libdrm legge OF_FULLNAME/OF_COMPATIBLE in quel file
   per enumerare il dispositivo; il diniego impedisce di scoprire la GPU Vulkan.
   Sono aggiunte quattro regole genfscon per i soli uevent di GPU 206400000.gpu
   e DCP soc:display-subsystem, nelle due disposizioni del parent platform.
   Il tipo è sysfs_gpu: i client gpu_sphal_domain hanno già i permessi di lettura.
   La shell riceve solo read/open/getattr su questo tipo per la diagnostica.

Le regole sono centralizzate in `scripts/apple_graphics_policy.py`. Non sono
aggiunti accessi generici a sysfs né modalità permissive. Le etichette effettive
dei due file sul Mac saranno controllate nella prossima cattura.

Verifica effettuata con le immagini reali in Android/QEMU, enforcing:
`googlebook-labelprobe` usa libselinux per risolvere i contesti di card0, card1,
card3, card137, renderD128 e renderD130 e interroga la policy caricata per gli
accessi di SurfaceFlinger, gpuservice, allocator e composer. Tutti i controlli
sono passati. Ricevuta `.work/graphics-selinux-validation.json`, legata agli hash
kernel/vendor/system_ext, obbligatoria nell'installer anche in modalità bring-up.
La verifica non emula un lavoro AGX né conferma ancora i percorsi genfs fisici.

Per la prossima prova è incluso un test Vulkan nativo una tantum, attivato solo
con debug=1 e ro.hardware.vulkan=asahi. Gira come gpu_service (UID1072), nel
dominio gpuservice originale mediante etichetta gpuservice_exec; scrive in
logcat con tag googlebook-vulkan. Ha timeout init di 25 secondi. Il dominio
è stato verificato in QEMU; lì termina correttamente con nessun device Apple.

Il test richiede driverID MESA_HONEYKRISP (26) e tipo GPU integrata: non accetta
una CPU SwiftShader come prova GPU. Crea un dispositivo/queue Vulkan, alloca un
buffer, invia vkCmdFillBuffer, aspetta la queue e controlla i dati risultanti.
Honeykrisp dichiara vendorID Mesa (0x10005), quindi il test verifica driverID
e tipo dispositivo, non il vendor PCI Apple. Solo VULKAN_SMOKE_PASS con
queste proprietà attesterebbe quel lavoro.
Non prova ancora EGL, importazione AHardwareBuffer o la presentazione DCP.

Il nuovo android_hardware_watch.sh registra ls -lZ dei nodi DRM, il percorso
canonico e l'etichetta dei due uevent, i risultati del matcher/policy e il tag
googlebook-vulkan, oltre a logcat e stato boot. Mantenere lo stesso percorso
USB con DTB corretto dell'ultima cattura; lo stage 2 abbinato su disco resta
invariato. Sono aggiornati solo vendor/system_ext dentro super e documentazione
su EFI-GOS, con backup e rilettura verificata dall'installer. Non è dichiarato
un boot Android completo prima della prossima prova.
