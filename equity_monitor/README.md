# Equity Monitor

Le cahier des charges complet (prompt v3) est dans `PROMPT_EQUITY_MONITOR.md`.

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
par `fetch` quand il est servi par un serveur / publié. Les graphiques utilisent la copie
locale `lib/plotly.min.js` (Plotly 2.35.2, MIT) ; cdnjs n'est appelé qu'en secours, le
dashboard fonctionne donc hors ligne.

Options : `--skip-breadth`, `--skip-options`, `--skip-13f`, `--skip-wiki`, `--skip-rty` réutilisent le
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
| `sectors.json` | rotation sectorielle US (11 SPDR vs S&P 500, RSP) et Europe (18 iShares STOXX Europe 600 sectoriels vs ^STOXX) : perf absolue et relative, momentum 12-1 et rang, RRG simplifié avec traces, paires cycliques/défensives, score d'entrée sur 6 conditions avec références |
| `baskets.json` | paniers thématiques US (Mag7, hyperscalers, neo-clouds, mémoire, photonique, Leopold 13F) : indice équipondéré, perf, relatif au benchmark, z du ratio, betas, largeur, membres ; matrice « qui bat qui » et paires relatives |
| `asia.json` | séance asiatique → séance US : corrélations et betas sur gap / intraday / close-close, beta partiel, taux de signes, moyennes conditionnelles, règle ouverture→clôture, corrélations glissantes |
| `constituents_stats.json` | statistiques par titre des constituants SPX / NDX (et RTY si `inputs/IWM_holdings.csv` est présent), agrégats sectoriels |
| `flows.json` | volumes anormaux (actions, ETF thématiques, ETF sectoriels US) : ratio et z 20 j, volume dollars, hausse/baisse 10 j, OBV ; proxy de flux, Yahoo n'ayant pas les parts en circulation |
| `alerts.json` | alertes classées (idio ≥ 2 σ, croisement MM du jour, |z| ratio ≥ 2, quadrant RRG, Asie ≥ ±2 %, fenêtre Asie futures ≥ ±1 %, réaction post-earnings hors implicite, RSI extrême) |
| `implied_history.json` | move implicite mémorisé par titre et date de résultats (sert à l'alerte post-earnings) |
| `cusip_cache.json` | mapping CUSIP → ticker OpenFIGI persistant (Russell 2000) |
| `backtest.json` | momentum US (avec / sans panier 13F), mean reversion Europe, et rotation sectorielle (top 3 momentum 12-1 mensuel, avec / sans filtre Faber, US et Europe), in/out-of-sample, frais et slippage |
| `run_status.json` | étapes, erreurs, journal par symbole, séries sans clôture, lecture du marché |
| `data.js` | les dix fichiers ci-dessus dans `window.EQUITY_MONITOR_DATA` |

## Conventions de calcul

- Rendements sur clôtures ajustées ; 1M = 21 séances, 3M = 63, 1 an = 252. Momentum 12-1 = P[t−21] / P[t−252] − 1.
- RSI 14 de Wilder (lissage exponentiel alpha = 1/14) ; croisements MM20/50 et MM50/200 : état, écart et dernier croisement (date, séances écoulées).
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
- Rotation sectorielle : force relative = ETF / indice ; RS-ratio = ratio / MM50 du ratio × 100, RS-momentum = RS-ratio / RS-ratio[−10] × 100
  (quadrants Leading / Weakening / Lagging / Improving) ; score d'entrée sur 6 conditions (Moskowitz-Grinblatt 12-1, Faber MM200,
  Antonacci momentum absolu, George-Hwang plus haut 52 s., RRG, Jegadeesh renversement 1 mois) ; entrée = top 3 du 12-1 + score ≥ 4 +
  tendance intacte ; sortie = secteur détenu passé sous MM200 ou en Weakening ; références dans `monitor_config.json → sector_signals`.
- Les barres datées du jour du run sont exclues (pas encore de clôture).
- Backtest : hebdomadaire, long only, frais 5 bp + slippage 5 bp par côté sur le turnover,
  in-sample = 60 % de l'historique. Le panier 13F est connu après coup : son résultat est
  présenté séparément et marqué comme biaisé.

## Russell 2000

Composition lue automatiquement dans le dernier N-PORT-P public de l'iShares Russell 2000 ETF (EDGAR), CUSIP convertis par OpenFIGI avec cache (`cusip_cache.json`). Première passe sans clé OpenFIGI : ~9 minutes ; ensuite quelques secondes. `--skip-rty` réutilise la composition précédente. Un export iShares `inputs/IWM_holdings.csv` déposé à la main reste prioritaire.

## Non fait (idées)

Alertes sur changement de quadrant RRG ; beta sectoriel du panier 13F ; calendrier macro (FOMC, CPI, NFP, BCE) ; upgrades / downgrades datés (`upgrades_downgrades`) ;
attribution du panier 13F par thème ; alertes (idio > 2 σ, move post-earnings hors du move implicite).
