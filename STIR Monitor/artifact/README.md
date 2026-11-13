# STIR Monitor (Claude artifact)

Source of the live dashboard published at https://claude.ai/artifact/VAo6aNQ4St62JpjfVc9F94
(a Claude "Data" artifact). Every number is fetched from IBKR through the
"Interactive Brokers (IBKR)" connector when the page is opened, with the viewer's own access.

- `index.html`, `style.css`: page layout and styles (IBM Plex Mono is embedded in `fonts.css`, not kept here)
- `loaders.js`: one loader per dataset. It calls `get_price_history` for each contract in a strip
  (generated from `contracts.json` by `gen_loaders.py`)
- `calc.js`: maths (bp changes, Dec spreads, the FedWatch-style Fed path, the CORRA strip fit)
- `app.js`: calcs and drawings
- `datasets.json`: the dataset definitions written to the artifact
