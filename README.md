# Shift Scheduling Clinica

Repository di supporto al progetto di pianificazione turni per una clinica
ospedaliera. Il codice fornisce tre blocchi principali:

* **Loader (`loader/`)** – normalizza i file CSV di input e costruisce i
  DataFrame necessari al solver.
* **Preprocessing (`src/preprocessing/`)** – calcola i bilanci progressivi e i
  coefficienti di penalità dinamici richiesti dal modello.
* **Modello (`src/model/`)** – definisce il problema CP-SAT con vincoli su orari,
  notti, riposi e fairness, come descritto nella documentazione di progetto.

La cartella `data/` contiene esempi di input, mentre `scripts/` raccoglie gli
strumenti di validazione per i dati e le configurazioni.

## Requisiti

Prima di eseguire il loader assicurarsi di installare le dipendenze Python:

```bash
pip install -r requirements.txt
```

## Utilizzo

Per eseguire l'intero caricamento dati usando i file CSV forniti nella cartella
`data/`:

```bash
python -m loader --config config.yaml --data-dir data
```

Opzionalmente è possibile esportare i DataFrame intermedi in CSV di debug:

```bash
python -m loader --config config.yaml --data-dir data --export-csv
```

I file verranno salvati nella cartella `_expanded` all'interno della directory
dati. Per scegliere una destinazione alternativa è possibile indicare
`--export-dir` (percorso assoluto o relativo alla directory dati).

Il loader può essere integrato nel solver principale tramite la funzione
`load_context` che restituisce un `ModelContext` pronto per la risoluzione.

### Pianificazione su sottoinsieme reparti

È possibile limitare la schedulazione a un sottoinsieme dei reparti configurati:

- da CLI con `--departments`, passando un elenco separato da virgole
  (es. `--departments degenza,ambulatorio`);
- da configurazione con `scheduling.selected_departments` in `config.yaml`;
- da UI Streamlit con il campo testuale "Reparti da includere (CSV, opzionale)".

Quando la selezione è attiva, il loader filtra coerentemente i dati:

- `employees` solo dei reparti selezionati;
- `month_plan` e slot solo dei reparti selezionati;
- vincoli/requirements/locks/history/assenze/preassignments solo relativi a
  dipendenti e slot rimasti;
- pool di copertura limitati ai reparti selezionati, evitando movimenti cross
  verso reparti esclusi.


## Limiti orari caricati per dipendente

Il loader normalizza tutti i valori orari in minuti e mette a disposizione tre
grandezze da usare nei vincoli del solver:

* **`dovuto_min`** – le ore teoriche mensili previste dal contratto. Il valore è
  letto da `employees.csv` (colonna `ore_dovute_mese_h`) oppure dal default
  `defaults.contract_hours_by_role_h` indicato in `config.yaml`.
* **`max_month_min`** – il limite mensile inderogabile. Quando non è presente
  l'override `max_month_hours_h` nel CSV, viene calcolato come `1.25 × ore
  contrattuali mensili`, permettendo una tolleranza del 25% rispetto al dovuto.
* **`max_week_min`** – il limite settimanale inderogabile. Se il CSV non fornisce
  un override (`max_week_hours_h`), il loader parte dalle ore contrattuali
  mensili e le ripartisce su una settimana "media" del mese usando la formula
  `ore_mese / giorni_mese(start_date) × 7`. Il cap finale è `1.4 × quota settimanale` e
  viene applicato anche alle settimane parziali (iniziali/finali), così da
  impedire concentrazioni eccessive di straordinario in una singola settimana
  senza imporre limiti artificiali sui singoli giorni.

Gli stessi controlli sono replicati nello script `scripts/check_data.py`, in
modo da intercettare eventuali override errati prima dell'esecuzione del loader.

## Pesi delle penalità

Il file `config.yaml` espone una sezione unica `weights` con tutti i pesi delle
penalità soft del modello, così da permettere il tuning senza modifiche al
codice.

Chiavi disponibili:

- `weights.fairness_night` e `weights.fairness_weekend` per la fairness su
  notti e weekend/festivi.
- `weights.night_single_recovery` per i pattern post-notte.
- `weights.rest11` e `weights.weekly_rest` per i vincoli di riposo.
- `weights.night_extra_consecutive` per la penalità sulle notti consecutive
  oltre soglia.
- `weights.cross` per i turni cross-reparto.
- `weights.preassignment_change` per la stabilità rispetto alle preassegnazioni.
- `weights.due_hours`, `weights.due_hours_under`, `weights.due_hours_over` e
  `weights.final_balance` per l'equilibrio ore.

Tutti i valori devono essere numeri non negativi; impostando un peso a `0` la
relativa penalità viene disattivata.

Per retrocompatibilità, i vecchi campi sono ancora accettati in lettura.
