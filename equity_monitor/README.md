# Equity Monitor

Dashboard buy-side (long only, horizon semaines-mois) ouvert chaque matin avant Londres.
Question de fond : qu'est-ce qui a bougé, est-ce du beta ou de l'idiosyncratique, et quel
événement arrive qui peut changer la thèse ?

## Lancer

```bash
py -3.13 -m pip install yfinance pandas numpy requests beautifulsoup4 lxml
py -3.13 update_monitor.py          # ~5 min : prix, fondamentaux, options, 13F, Wikipédia, breadth
py -3.13 backtest_signals.py        # backtest.json à partir de prices.json
py -3.13 update_monitor.py --bundle-only   # régénère data.js (lecture du dashboard en file://)
```

`run_monitor.cmd` enchaîne les trois (log par run dans `logs/`, `LAST_ERROR.txt` et
`run_status.json` en cas d'échec). Tâche planifiée Windows, lundi-vendredi 06:45 UTC :

```bat
schtasks /Create /TN "EquityMonitor" /TR "\"C:\chemin\equity_monitor\run_monitor.cmd\"" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 06:45 /F
```

(Si le PC n'est pas en UTC, convertir 06:45 UTC en heure locale ; l'ancrage UTC est à
maintenir à la main lors des changements d'heure.)

Puis ouvrir `index.html` : il lit `Sources du dashboard/data.js` (file://) ou les JSON
par `fetch` quand il est servi par un serveur / publié.

Options : `--skip-breadth`, `--skip-options`, `--skip-13f`, `--skip-wiki` réutilisent le
fichier du run précédent (marqué comme tel dans `run_status.json`).

Avant de lancer, remplacer dans `monitor_config.json` le `sec.user_agent` par votre nom et
votre email (exigence SEC). Une clé OpenFIGI dans la variable `OPENFIGI_API_KEY` est
facultative (sans clé : 10 CUSIP par requête, 25 requêtes par minute).

## Sources (API uniquement)

| Donnée | Source | Appel |
|---|---|---|
| Prix, FX, indices, ETFs, VIX / VXN | yfinance | `yf.download` par lots de 40, reprise sur erreur, puis symbole par symbole pour les manquants |
| Fondamentaux, estimations, révisions | yfinance | `info`, `earnings_estimate`, `revenue_estimate`, `eps_trend`, `eps_revisions`, `calendar` |
| Historique des earnings | yfinance | `get_earnings_dates(limit=60)` (heure locale → AMC / BMO) |
| Move implicite, IV 30 j | yfinance | `option_chain` : straddle ATM de la 1re échéance après publication ; IV dérivée du straddle (Black-Scholes, r = 0) car la colonne `impliedVolatility` de Yahoo est vide hors séance |
| Panier 13F | SEC EDGAR | `data.sec.gov/submissions` → dernier 13F-HR → `form13fInfoTable.xml` ; User-Agent nom + email ; ≤ 8 req/s |
| CUSIP → ticker | OpenFIGI v3 | `ID_CUSIP`, `ID_CINS` pour les émetteurs étrangers (1re lettre alphabétique) |
| Compositions SPX, NDX, SX5E, DAX, CAC, FTSE | Wikipédia | API MediaWiki `action=parse`, Retry-After honoré sur 429, repli sur le fichier précédent |
| VSTOXX | — | n/a : pas distribué par Yahoo, la raison est écrite dans `risk.json` |

Chaque fichier porte `generated_at` et chaque enregistrement `fetched_at`. Valeur
manquante = `null` → « — » dans le dashboard. Clôture absente pour la veille ouvrée =
`stale: true` → date en orange. Yahoo publie les clôtures des lignes européennes (ETFs
LSE/Xetra, actions européennes) avec un décalage de quelques heures : à 06:45 UTC elles
sont souvent encore à J−2, le dashboard le montre tel quel.

## Fichiers générés (`Sources du dashboard/`)

| Fichier | Contenu |
|---|---|
| `universe.json` | groupes, symboles, devises, clés d'indices ; panier 13F construit depuis `sa_13f.json` |
| `prices.json` | clôtures ajustées 5 ans par symbole, `last_close_date`, `stale` |
| `quotes.json` | stats de marché, beta SPX, idio 1M/3M, valorisation, croissance, qualité, sentiment, poids 13F |
| `events.json` | prochaines publications (date, AMC/BMO, consensus, move implicite vs historique), réactions 12 trimestres, calendrier 30 j (ex-div, 13F, échéances options, rebalancement S&P) |
| `breadth.json` | % > MM50 / MM200, plus hauts 20 j, ligne A/D 3M, EW − CW, Mag7 vs reste, biais de survie |
| `constituents.json` | compositions Wikipédia converties au format Yahoo, tickers non résolus |
| `sa_13f.json` | positions longues en actions, poids, changements vs trimestre précédent, mapping OpenFIGI, appels SEC |
| `risk.json` | betas (SPX/NDX/SOX, 1 an, 3 mois, hebdo, downside, R², vol idio), vol implicite vs réalisée, corrélations 60 j, signaux, lecture du marché |
| `backtest.json` | momentum US (avec / sans panier 13F) et mean reversion Europe, in/out-of-sample, frais et slippage |
| `run_status.json` | étapes, erreurs, journal par symbole, séries sans clôture, lecture du marché |
| `data.js` | les dix fichiers ci-dessus dans `window.EQUITY_MONITOR_DATA` |

## Conventions de calcul

- Rendements sur clôtures ajustées ; 1M = 21 séances, 3M = 63, 1 an = 252.
- Betas sur log-rendements **en USD** (GBp / 100 × GBPUSD, EUR × EURUSD). Le beta hebdo
  (W-FRI, 52 semaines) corrige la non-synchronicité Londres / New York.
- Idio 1M = perf 1M − β(1 an) × SPX 1M. Le même découpage est fait sur 3M.
- Réaction aux earnings : AMC = clôture J → J+1, BMO = J−1 → J ; anormale = réaction −
  β(1 an avant l'événement) × SPX ; PEAD 5 / 20 séances après la réaction.
- Move implicite = (call ATM + put ATM) / spot sur la 1re échéance après publication ;
  prix mid si bid/ask cotés, sinon dernier traité (`implied_move_basis`).
- Signaux : momentum US = prix > MM50 > MM200, perf 3M − SPX 3M > seuil, idio 1M > seuil ;
  mean reversion Europe = z-score 20 j et RSI 14 sous les seuils. Seuils dans
  `monitor_config.json`, modifiables en direct dans l'onglet Beta & risque. Astérisque si
  résultats ≤ 5 j.
- Backtest : hebdomadaire, long only, frais 5 bp + slippage 5 bp par côté sur le turnover,
  in-sample = 60 % de l'historique. Le panier 13F est connu après coup : son résultat est
  présenté séparément et marqué comme biaisé.

## Non fait (idées)

Calendrier macro (FOMC, CPI, NFP, BCE) ; upgrades / downgrades datés (`upgrades_downgrades`) ;
attribution du panier 13F par thème ; alertes (idio > 2 σ, move post-earnings hors du move implicite).
