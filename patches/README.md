# Patch del port

`googlebook-port.patch` in ciascuna sottocartella è la patch aggregata contro il commit corrispondente in `manifests/upstreams.json`. Gli snapshot in `sources/` permettono di leggere direttamente i file modificati. Gli UUID delle partizioni nel kernel pubblico sono esempi.

Per una verifica senza modificare l’albero:

```sh
git -C /path/to/linux-asahi apply --check /path/to/repo/patches/linux-asahi/googlebook-port.patch
git -C /path/to/mesa apply --check /path/to/repo/patches/mesa/googlebook-port.patch
```

Dopo aver verificato il commit corretto, le patch possono essere applicate con gli stessi comandi senza `--check`.

Le patch `privileged-priority.patch` isolano la nuova funzione per revisione. La patch Mesa isolata presuppone l’integrazione Android/two-queue già presente; quella aggregata parte direttamente dall’upstream fissato. `android-vulkan-full.patch` raccoglie l’integrazione Vulkan senza gli adattamenti preesistenti dei compilatori host. Sono alternative per revisione e composizione: non vanno applicate tutte una dopo l’altra allo stesso albero.

Le correzioni DRM fence mantengono anche le patch e i riferimenti originali. La patch aggregata del kernel le comprende già. Il futuro riallineamento upstream dell’estensione UAPI delle priorità deve coordinare kernel e Mesa.
