# Security and operational boundaries

`jev-codebook` sends the text of each response, plus your codebook definitions and examples, to `https://api.typesafe.ai/v1/systemone` when run without `--fake`. You own consent and data-protection obligations for that text (survey answers and reviews can contain personal data): pseudonymize or drop identifying fields before coding, keep the `id` column meaningful only to you, and remember that `--cache` and `--out` store the text on disk.

The key is read from `TYPESAFE_API_KEY`, sent only as a bearer header over HTTPS, never logged, and redacted from error messages. Redirects are refused. Plain `http://` is accepted only for `127.0.0.1`/`localhost` test servers. Do not commit `.jev-cache*`, coded outputs or `.env` files.

A model probability is not a calibrated guarantee. Thresholds are yours to calibrate with `tune` on your own labeled sample, and the review queue is the intended human check.

Report a vulnerability through GitHub private vulnerability reporting on this repository when enabled; otherwise open a minimal issue asking for a private channel, without exploit details or credentials. This is a public alpha without a security audit or support SLA.
