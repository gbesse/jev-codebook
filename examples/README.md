Synthetic example dataset for the offline demo and tests. Nothing here is real customer data.

- `codebook.json`: 6-code multi-mode codebook for feedback about the "Orbit" desk lamp by the fictional brand Halden; thresholds are illustrative.
- `responses.csv`: 41 rows (`id,text,channel`): 40 synthetic responses plus one blank row (`r41`) to show that blank texts are skipped. The `channel` column is ignored by the tool.
- `fixtures.json`: synthetic per-code probabilities for `FakeJev`, keyed by exact response text. Not Jev output.
- `human.csv`: synthetic "human coder" labels (0/1 per code), derived from the fixtures with six deliberate disagreements so the agreement table is not trivially perfect.
- `offline_demo.py`: `python -m examples.offline_demo` from the repository root.
- `support_codebook.json`, `support_responses.csv`, `support_fixtures.json`: five fictional support messages for a single-label triage example, including an uncertain message and a message outside the codebook. Probabilities are synthetic, not Jev output.
- `single_mode_demo.py`: `python -m examples.single_mode_demo` shows the chosen option, assigned category and human-review flag separately.
