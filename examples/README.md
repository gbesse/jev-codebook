Synthetic example datasets for the offline demos and tests. Nothing here is real customer data.

**Start here / Commencez ici / Empieza aquí:** run `python3 -m examples.single_mode_demo` from the repository root. The five support messages show assignment, human review and abstention without a key or network access. / Les cinq messages d’assistance montrent l’attribution, la revue humaine et l’abstention sans clé ni accès réseau. / Los cinco mensajes de soporte muestran asignación, revisión humana y abstención sin clave ni acceso a la red.

- `codebook.json`: 6-code multi-mode codebook for feedback about the "Orbit" desk lamp by the fictional brand Halden; thresholds are illustrative.
- `responses.csv`: 41 rows (`id,text,channel`): 40 synthetic responses plus one blank row (`r41`) to show that blank texts are skipped. The `channel` column is ignored by the tool.
- `fixtures.json`: synthetic per-code probabilities for `FakeJev`, keyed by exact response text. Not Jev output.
- `human.csv`: synthetic "human coder" labels (0/1 per code), derived from the fixtures with six deliberate disagreements so the agreement table is not trivially perfect.
- `offline_demo.py`: `python -m examples.offline_demo` from the repository root.
- `support_codebook.json`, `support_responses.csv`, `support_fixtures.json`: five fictional support messages for a single-label triage example, including an uncertain message and a message outside the codebook. Probabilities are synthetic, not Jev output.
- `single_mode_demo.py`: `python -m examples.single_mode_demo` shows the chosen option, assigned category and human-review flag separately.
