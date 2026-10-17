#!/usr/bin/env python3
"""Bundle the exact prepared boot files and diagnostics for the receiving Mac."""
import datetime
import gzip
import hashlib
import json
import pathlib
import shutil
import zipfile
from boot_config import BOOT_ARGS

BASE = pathlib.Path(__file__).resolve().parents[1]


def sha(path):
    with path.open('rb') as inp:
        return hashlib.file_digest(inp, 'sha256').hexdigest()


def main():
    bundle = BASE/'dist/GoogleBook-USB-Debug'
    bundle.mkdir(exist_ok=True)
    # Remove old generated artifacts so a new archive cannot contain stale
    # successful-boot claims or a previous assembled m1n1 payload.
    for name in ['ANDROID_BOOT_TEST.json', 'DEBUG_ANDROID.txt', 'm1n1-googlebook-guest.bin']:
        (bundle/name).unlink(missing_ok=True)
    image = (BASE/'apple_silicon_boot/Image').read_bytes()
    (bundle/'Image.gz').write_bytes(gzip.compress(image, compresslevel=9, mtime=0))
    for name in ['initrd.img', 't8103-j293.dtb']:
        shutil.copyfile(BASE/'apple_silicon_boot'/name, bundle/name)
    for name in ['boot_usb_debug.py', 'capture_uart.py', 'android_hardware_watch.sh']:
        shutil.copyfile(BASE/'scripts'/name, bundle/name)
    shutil.copyfile(BASE/'CONFIGURAZIONE_E_MODIFICHE_M1.md', bundle/'CONFIGURAZIONE_E_MODIFICHE_M1.md')
    shutil.copyfile(BASE/'.work/selinux-smoke-results.json', bundle/'KERNEL_SMOKE_TESTS.json')
    (bundle/'bootargs.txt').write_text(BOOT_ARGS+'\n')
    (bundle/'ISTRUZIONI.txt').write_text('''GOOGLEBOOK OS — PROVA HARDWARE DIAGNOSTICA, KERNEL #12

Il desktop Android completo e la GPU Apple NON sono ancora validati.
Questo pacchetto contiene gli stessi kernel/initrd preparati per EFI-GOS.
La configurazione e le limitazioni sono nel Markdown incluso.

Sul Mac ricevente usare il proprio ambiente Python con pyserial e construct.
Collegare il target tramite USB-C dati. Le porte possono avere nomi diversi:
P_01 e il proxy primario; P_03 e la UART secondaria. Non aprire la stessa
porta con due programmi.

1. Prima di avviare il guest, nel terminale del Mac ricevente:

python3 capture_uart.py /dev/cu.usbmodemP_03 --commands-file android_hardware_watch.sh

La cattura conserva i byte su disco e si riconnette dopo un reset. Quando la
console Android segnala GOS_CONSOLE_READY, invia i comandi per registrare anche
logcat, driver DRM e avanzamento del boot. Non richiede una shell root.

2. Se si usa il percorso m1n1 hypervisor, in un altro terminale:

python3 boot_usb_debug.py /percorso/al/proprio/m1n1 --device /dev/cu.usbmodemP_01

Il target deve essere in proxy e il proprio m1n1 deve essere gia compilato e
compatibile. Il wrapper carica m1n1 in RAM, non lo installa. Il test hypervisor
puo differire dall'avvio nativo, anche nell'attivazione di DCP/AGX.

IMPORTANTE DOPO LA CATTURA KERNEL #12: il vecchio payload U-Boot guest passato
a launch_hv.py consegna un device tree che espone solo apple,agx-g13g, mentre
il driver richiede apple,agx-t8103. Aggiornare solo Image non aggiorna quel DT.
Per questa prova usare il wrapper sopra con il DTB incluso, che m1n1 completa
prima di passarlo al kernel. Non riutilizzare uboot-hv-cb1024.raw invariato.
Non forzare il DTB statico direttamente da GRUB: mancherebbero i fixup runtime.

3. Conservare l'intero file googlebook-uart-DATA-ORA.log. Ctrl+C ferma la cattura
sul Mac ricevente. panic=0 ferma un panic kernel, ma non ogni riavvio richiesto
da Android. Il vecchio logger in /metadata/googlebook-logs non e affidabile.

Per la prova nativa scegliere UEFI e GoogleBook OS. Non caricare manualmente
un DTB statico al posto del device tree completato da m1n1/U-Boot.
''')
    kernel_hash = hashlib.sha256(image).hexdigest()
    smoke = json.loads((bundle/'KERNEL_SMOKE_TESTS.json').read_text())
    assert smoke['kernel_sha256'] == kernel_hash
    result = {
        'revision': 'kernel12-diagnostic-hardware-bringup',
        'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'target': 'MacBookPro17,1 / J293 / Apple M1',
        'installed_kernel_sha256': kernel_hash,
        'installed_initrd_sha256': sha(bundle/'initrd.img'),
        'full_android_boot_validated': False,
        'apple_gpu_validated': False,
        'hardware_capture_tested_this_revision': False,
        'kernel_smoke_tests': smoke,
        'files_sha256': {p.name: sha(p) for p in sorted(bundle.iterdir())
                         if p.is_file() and p.name != 'manifest.json'}}
    (bundle/'manifest.json').write_text(json.dumps(result, indent=2)+'\n')
    archive = BASE/'dist/GoogleBook-USB-Debug.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(bundle.iterdir()):
            if path.is_file():
                z.write(path, bundle.name+'/'+path.name)
    print('USB_DIAGNOSTIC_BUNDLE:', archive)


if __name__ == '__main__':
    main()
