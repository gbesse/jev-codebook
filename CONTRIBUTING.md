# Contributing

Open an issue with a redacted, synthetic reproduction (codebook, a few rows, the command). Never post real respondent text or a key.

Before proposing a change run `python -m compileall -q src tests && python -m unittest discover -s tests && python -m examples.offline_demo`. Add a focused unittest when touching decision rules, statistics, file formats or client error handling; statistics changes must keep the textbook-value tests green. Keep the runtime stdlib-only and every external call behind an explicit timeout. Start every new file with a `# Purpose:` header and explain the why of non-obvious logic in docstrings. Update `ai/CHANGELOG.md` with the purpose and key decisions, and never describe an untested capability as verified.
