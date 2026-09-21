# Purpose: `jev-codebook` command line: validate, estimate, code, agreement, tune, report.
"""Command line interface.

Every subcommand prints results to stdout and problems to stderr with a
non-zero exit code. Nothing here decides anything: the CLI only wires files
to the library functions.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from . import __version__
from .agreement import compute_agreement, tune_thresholds
from .cache import ExactInputCache
from .client import DEFAULT_ENDPOINT, DEFAULT_MODEL, FakeJev, JevClient, JevError, RateLimiter
from .codebook import CodebookError, load_codebook
from .coder import code_responses, estimate_run
from .datafiles import CodedRecord, CodedWriter, DataError, read_coded, read_human_labels, read_responses
from .report import cooccurrence, frequencies, top_uncertain
from .stats import fmt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jev-codebook", description="Apply a qualitative codebook to open text with Jev.")
    parser.add_argument("--version", action="version", version=f"jev-codebook {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="check a codebook JSON file")
    p.add_argument("codebook")

    p = sub.add_parser("estimate", help="tokens, requests and estimated cost; no call")
    p.add_argument("responses")
    p.add_argument("--codebook", required=True)
    _input_options(p)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("code", help="code responses with Jev (or --fake fixtures)")
    p.add_argument("responses")
    p.add_argument("--codebook", required=True)
    p.add_argument("--out", required=True, help="coded CSV; existing ids are skipped (resume)")
    p.add_argument("--review", help="CSV receiving only the rows flagged for review")
    p.add_argument("--cache", help="exact-input cache file, e.g. .jev-cache.json")
    p.add_argument("--fake", help="fixtures JSON: use the offline fake provider instead of Jev")
    p.add_argument("--concurrency", type=int, default=8)
    p.add_argument("--rate-limit", type=int, default=1000, help="max requests per minute (default 1000)")
    p.add_argument("--timeout", type=float, default=30.0, help="seconds per request")
    p.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--no-resume", action="store_true", help="fail if --out already exists instead of resuming")
    _input_options(p)

    p = sub.add_parser("agreement", help="inter-rater statistics against human labels")
    p.add_argument("coded")
    p.add_argument("human")
    p.add_argument("--codebook", required=True)
    p.add_argument("--use-thresholds", action="store_true", help="re-decide from p_<code> with the codebook thresholds instead of the stored 0/1")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("tune", help="choose per-code thresholds on a tuning split, evaluate on holdout")
    p.add_argument("coded")
    p.add_argument("human")
    p.add_argument("--codebook", required=True)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--tune-fraction", type=float, default=0.6)
    p.add_argument("--write-codebook", help="write a copy of the codebook with the tuned thresholds")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("report", help="frequencies, co-occurrence and most uncertain rows")
    p.add_argument("coded")
    p.add_argument("--codebook", help="use the codebook thresholds to rank uncertainty (default 0.5)")
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--json", action="store_true")
    return parser


def _input_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("--id-column", default="id")
    p.add_argument("--text-column", default="text")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handler = {
        "validate": cmd_validate,
        "estimate": cmd_estimate,
        "code": cmd_code,
        "agreement": cmd_agreement,
        "tune": cmd_tune,
        "report": cmd_report,
    }[args.command]
    try:
        return handler(args)
    except (CodebookError, DataError, JevError, OSError, ValueError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("interrupted; --out keeps the rows completed so far", file=sys.stderr)
        return 130


def cmd_validate(args) -> int:
    cb = load_codebook(args.codebook)
    print(f"ok: codebook '{cb.name}' v{cb.version}, {len(cb.codes)} codes, mode {cb.mode}, review band {list(cb.review_band)}")
    for c in cb.codes:
        print(f"  {c.id:<24} threshold {c.threshold:.2f}  {c.label}")
    return 0


def cmd_estimate(args) -> int:
    cb = load_codebook(args.codebook)
    data = read_responses(args.responses, id_column=args.id_column, text_column=args.text_column)
    est = estimate_run(data.responses, cb)
    est.skipped_blank = data.skipped_blank
    if args.json:
        print(json.dumps({"responses": est.responses, "skipped_blank": est.skipped_blank, "requests": est.requests, "input_tokens": est.input_tokens, "estimated_cost_usd": est.estimated_cost_usd}, indent=2))
        return 0
    print(f"responses: {est.responses} (blank skipped: {est.skipped_blank})")
    print(f"requests:  {est.requests}")
    print(f"tokens:    ~{est.input_tokens:,} input (chars/4 estimate)")
    print(f"cost:      ~USD {est.estimated_cost_usd:.4f} (estimate from the published price list, output tokens are free)")
    return 0


def _make_provider(args):
    if args.fake:
        return FakeJev.from_file(args.fake)
    return JevClient(endpoint=args.endpoint, model=args.model, timeout_seconds=args.timeout, rate_limiter=RateLimiter(args.rate_limit))


def cmd_code(args) -> int:
    cb = load_codebook(args.codebook)
    data = read_responses(args.responses, id_column=args.id_column, text_column=args.text_column)
    if args.no_resume and os.path.exists(args.out):
        raise DataError(f"{args.out} already exists (remove it or drop --no-resume)")
    already = read_coded(args.out).ids if os.path.exists(args.out) and os.path.getsize(args.out) > 0 else set()
    todo = [r for r in data.responses if r.id not in already]
    provider = _make_provider(args)
    cache = ExactInputCache(args.cache) if args.cache else None
    if already:
        print(f"resuming: {len(already)} ids already in {args.out}, {len(todo)} to code", file=sys.stderr)
    if data.skipped_blank:
        print(f"skipped {data.skipped_blank} blank responses", file=sys.stderr)
    if not todo:
        print("nothing to code")
        return 0
    review_writer = CodedWriter(args.review, cb.code_ids) if args.review else None
    reviews = 0
    with CodedWriter(args.out, cb.code_ids) as writer:
        def on_row(row):
            nonlocal reviews
            record = CodedRecord(row.id, row.text, row.assigned, row.probabilities, row.review, row.request_id)
            writer.write(record)
            if row.review:
                reviews += 1
                if review_writer is not None:
                    review_writer.write(record)

        try:
            summary = code_responses(todo, cb, provider, cache=cache, concurrency=args.concurrency, on_row=on_row)
        finally:
            if review_writer is not None:
                review_writer.close()
    print(f"coded {len(summary.rows)} responses -> {args.out}")
    print(f"review: {reviews} flagged" + (f" -> {args.review}" if args.review else ""))
    print(f"requests: {summary.live_requests} live, {summary.cached_requests} cached" + (" (fake provider, synthetic probabilities)" if args.fake else ""))
    print(f"tokens: {summary.input_tokens:,} input; estimated cost USD {summary.estimated_cost_usd:.4f} (published price list)")
    return 0


def _print_metrics_table(per_code: dict[str, Any]) -> None:
    header = f"{'code':<24}{'n':>5}{'agree%':>8}{'kappa':>7}{'alpha':>7}{'prec':>7}{'[95% CI]':>16}{'recall':>8}{'[95% CI]':>16}{'F1':>7}"
    print(header)
    for code, m in per_code.items():
        print(
            f"{code:<24}{m.n:>5}{fmt(m.accuracy * 100, 1):>8}{fmt(m.kappa):>7}{fmt(m.alpha):>7}{fmt(m.precision):>7}"
            f"{'[' + fmt(m.precision_ci[0]) + ', ' + fmt(m.precision_ci[1]) + ']':>16}{fmt(m.recall):>8}"
            f"{'[' + fmt(m.recall_ci[0]) + ', ' + fmt(m.recall_ci[1]) + ']':>16}{fmt(m.f1):>7}"
        )


def cmd_agreement(args) -> int:
    cb = load_codebook(args.codebook)
    coded = read_coded(args.coded)
    _check_codes(coded.code_ids, cb.code_ids, args.coded)
    human = read_human_labels(args.human, cb.code_ids)
    report = compute_agreement(coded, human, cb, use_thresholds=args.use_thresholds)
    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
        return 0
    print(f"matched {report.n_matched} ids (coded-only: {report.unmatched_coded}, human-only: {report.unmatched_human}); exact-match rate {fmt(report.exact_match_rate)}")
    _print_metrics_table(report.per_code)
    print("kappa/alpha: Cohen's kappa and Krippendorff's alpha (nominal, two coders) per code; intervals are Wilson 95%.")
    return 0


def cmd_tune(args) -> int:
    cb = load_codebook(args.codebook)
    coded = read_coded(args.coded)
    _check_codes(coded.code_ids, cb.code_ids, args.coded)
    human = read_human_labels(args.human, cb.code_ids)
    report = tune_thresholds(coded, human, cb, seed=args.seed, tune_fraction=args.tune_fraction)
    if args.write_codebook:
        tuned = cb.with_thresholds(report.thresholds)
        with open(args.write_codebook, "w", encoding="utf-8") as fh:
            json.dump(tuned.to_dict(), fh, indent=2, ensure_ascii=False)
            fh.write("\n")
    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
        return 0
    print(f"tuning split: {report.n_tune} rows, holdout: {report.n_holdout} rows (seed {report.seed}); thresholds chosen on the tuning split only")
    print(f"{'code':<24}{'current':>8}{'tuned':>7}{'tuneF1':>8}{'holdF1@cur':>12}{'holdF1@tuned':>14}{'holdKappa@tuned':>17}")
    for t in report.per_code:
        print(f"{t.code:<24}{t.current_threshold:>8.2f}{t.tuned_threshold:>7.2f}{fmt(t.tune_f1_at_tuned):>8}{fmt(t.holdout_current.f1):>12}{fmt(t.holdout_tuned.f1):>14}{fmt(t.holdout_tuned.kappa):>17}")
    if args.write_codebook:
        print(f"wrote {args.write_codebook}")
    return 0


def cmd_report(args) -> int:
    coded = read_coded(args.coded)
    thresholds = None
    if args.codebook:
        cb = load_codebook(args.codebook)
        _check_codes(coded.code_ids, cb.code_ids, args.coded)
        thresholds = {c.id: c.threshold for c in cb.codes}
    freqs = frequencies(coded)
    matrix = cooccurrence(coded)
    uncertain = top_uncertain(coded, thresholds, args.top)
    reviews = sum(1 for r in coded.records if r.review)
    if args.json:
        print(json.dumps({
            "n": len(coded.records),
            "review": reviews,
            "frequencies": [{"code": f.code, "count": f.count, "proportion": f.proportion, "ci95": list(f.ci95)} for f in freqs],
            "cooccurrence": matrix,
            "top_uncertain": [{"id": r.id, "distance": d, "probabilities": r.probabilities} for r, d in uncertain],
        }, indent=2))
        return 0
    print(f"{len(coded.records)} coded rows, {reviews} flagged for review")
    print(f"{'code':<24}{'count':>6}{'share':>7}{'[Wilson 95%]':>18}")
    for f in freqs:
        print(f"{f.code:<24}{f.count:>6}{fmt(f.proportion * 100, 1) + '%':>7}{'[' + fmt(f.ci95[0] * 100, 1) + '%, ' + fmt(f.ci95[1] * 100, 1) + '%]':>18}")
    print("co-occurrence (rows with both codes):")
    width = max(6, max(len(c) for c in coded.code_ids) + 1)
    print(" " * width + "".join(f"{c[:width - 1]:>{width}}" for c in coded.code_ids))
    for a in coded.code_ids:
        print(f"{a:<{width}}" + "".join(f"{matrix[a][b]:>{width}}" for b in coded.code_ids))
    print(f"most uncertain (distance to threshold {'from codebook' if thresholds else '0.5'}):")
    for r, d in uncertain:
        probs = " ".join(f"{c}={r.probabilities[c]:.2f}" for c in coded.code_ids)
        print(f"  {r.id:<10} d={d:.2f}  {probs}")
    return 0


def _check_codes(file_codes: list[str], codebook_codes: list[str], path: str) -> None:
    if set(file_codes) != set(codebook_codes):
        raise DataError(f"{path} codes {file_codes} differ from the codebook's {codebook_codes}")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
