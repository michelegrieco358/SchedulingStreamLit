# August infeasibility analysis (updated)

## Domanda
- I dati ufficiali di agosto (`month_plan.csv` + `coverage_roles.csv` + `shifts.csv`) richiedono **≈4 588 ore IP** e **≈6 905 ore OSS**.
- Ripartizione IP per reparto: REP0 ≈821,5 h; REP2/REP3/REP5 ≈1 255,5 h ciascuno. OSS: ADT ≈85 h, REP0 ≈263,5 h, REP2/REP3/REP5 ≈2 185,5 h ciascuno.

## Offerta e struttura
- Dopo gli 8 IP aggiuntivi ci sono **26 IP** e **52 OSS**. Con il cap implicito 1,25× sulle ore contrattuali i massimali duri sono **≈4 687,5 ore IP** e **≈9 465,6 ore OSS**: in aggregato basta per coprire la domanda.
- Il fabbisogno IP nei reparti con pochi effettivi resta comunque spostato: REP0/2/3 hanno **~1 645 h** complessive oltre la loro capacità locale (3 IP ciascuno), da bilanciare con i 17 IP di REP5.

## Verifica di fattibilità semplificata
- Un modello semplificato che considera copertura, un turno al giorno, cap mensile 1,25×, limite cross 30, riposi settimanali/bi-settimanali e limiti notti (8/mese, 2/settimana, max 3 consecutive) risulta **feasible/OPTIMAL** in <3 minuti, quindi questi vincoli da soli non spiegano l’infeasibilità del modello completo.【fa3b30†L1-L68】【e1907c†L1-L74】

## Probabile causa
- Restano vincoli più stringenti nel modello completo, in particolare il riposo minimo di 11h con sole 2 eccezioni mensili. Con le notti quotidiane (124 turni IP) ciò impone di saltare il giorno successivo a quasi tutte le notti e vieta sequenze P→M, riducendo drasticamente i slot disponibili nei reparti che già partono con 3 IP. È questa combinazione di riposo 11h + distribuzione di organico a rendere agosto ancora `INFEASIBLE` anche portando `cross.max_shifts_month` a 30.
