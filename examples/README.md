Synthetic example dataset for the offline demo and tests. Nothing here is real customer data.

- `codebook.json`: 6-code multi-mode codebook for feedback about the "Orbit" desk lamp by the fictional brand Halden; thresholds are illustrative.
- `responses.csv`: 41 rows (`id,text,channel`): 40 synthetic responses plus one blank row (`r41`) to show that blank texts are skipped. The `channel` column is ignored by the tool.
- `fixtures.json`: synthetic per-code probabilities for `FakeJev`, keyed by exact response text. Not Jev output.
- `human.csv`: synthetic "human coder" labels (0/1 per code), derived from the fixtures with six deliberate disagreements so the agreement table is not trivially perfect.
- `offline_demo.py`: `python -m examples.offline_demo` from the repository root.
