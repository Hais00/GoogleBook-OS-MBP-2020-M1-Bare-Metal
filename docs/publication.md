# Ambito della pubblicazione

Questo rilascio pubblica il codice locale del port e snapshot dei file upstream modificati. Le sorgenti upstream complete sono referenziate come submodule Git a commit espliciti; le patch aggregate descrivono le differenze. Non viene ancora fornita una procedura unica che ricostruisce esattamente l’intero sistema Android provato.

I manifest registrano sia l’hash del file locale di origine sia quello esportato. I percorsi privati sono stati sostituiti con percorsi schematici e gli identificativi delle partizioni con UUID di esempio. Le parti puramente GPU, incluse la nuova ABI della priorità e la gestione delle code, conservano il codice compilato. Le corrispondenze GPT pubblicate sono template, quindi il kernel pubblico richiede la configurazione delle partizioni prima dell’uso.

Le ricette in `scripts/` documentano il lavoro e restano in parte legate a una disposizione storica delle dipendenze. Gli strumenti privati che gestiscono la prenotazione del dispositivo e della UART non sono pubblicati. Alcuni test storici fanno riferimento a tali strumenti; non costituiscono una suite pubblica già unificata. La normalizzazione del build e dei test verrà fatta successivamente.

Il rilascio non contiene immagini Android, firmware Apple, HAL Google proprietari, binari compilati, recovery, super/userdata, chiavi, credenziali, indirizzi delle reti usate o log UART privati. L’eventuale distribuzione futura di un’immagine completa richiederà un inventario separato dei componenti e dei sorgenti corrispondenti.

Le note storiche conservano le fasi candidate e i risultati via via ottenuti. Per il risultato corrente usare `README.md`, `docs/status.md` e i report selezionati in `tests/results/`.
