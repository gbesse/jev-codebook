"""Export and apply explicit human decisions against an unchanged coding snapshot."""

from __future__ import annotations

import argparse
import copy
import csv
import io
import math
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .codebook import Codebook, load_codebook
from .datafiles import CodedFile, read_coded

TEXT = {
    "en": {
        "title": "Human review round trip",
        "invalid": "Invalid or stale review, codebook or output",
        "saved": "Human review files written",
        "help": "Show help and exit",
        "usage": "usage",
        "positional": "positional arguments",
        "options": "options",
        "source": "Source coded CSV",
        "book": "Original codebook JSON",
        "out": "New output file",
        "decisions": "Reviewed queue JSON",
        "audit": "New human-decision audit JSON",
        "include": "Include original text in the private review queue",
        "lang": "Report language",
        "scope": "No model call. Human assignments replace selected pending rows; model probabilities remain unchanged.",
    },
    "fr": {
        "title": "Aller-retour de revue humaine",
        "invalid": "Revue périmée ou invalide, codebook ou sortie invalide",
        "saved": "Fichiers de revue humaine enregistrés",
        "help": "Afficher l’aide et quitter",
        "usage": "utilisation",
        "positional": "arguments positionnels",
        "options": "options",
        "source": "CSV codé d’origine",
        "book": "Codebook JSON d’origine",
        "out": "Nouveau fichier de sortie",
        "decisions": "File JSON relue par un humain",
        "audit": "Nouveau journal JSON des décisions humaines",
        "include": "Inclure le texte original dans la file de revue privée",
        "lang": "Langue du rapport",
        "scope": "Aucun appel modèle. Les annotations humaines remplacent les lignes en attente sélectionnées ; les probabilités du modèle restent inchangées.",
    },
    "es": {
        "title": "Ida y vuelta de revisión humana",
        "invalid": "Revisión caducada o no válida, codebook o salida no válidos",
        "saved": "Archivos de revisión humana guardados",
        "help": "Mostrar ayuda y salir",
        "usage": "uso",
        "positional": "argumentos posicionales",
        "options": "opciones",
        "source": "CSV codificado original",
        "book": "Codebook JSON original",
        "out": "Archivo de salida nuevo",
        "decisions": "Cola JSON revisada por una persona",
        "audit": "Registro JSON nuevo de decisiones humanas",
        "include": "Incluir el texto original en la cola privada",
        "lang": "Idioma del informe",
        "scope": "Sin llamadas al modelo. Las anotaciones humanas sustituyen las filas pendientes seleccionadas; las probabilidades del modelo no cambian.",
    },
}


class ReviewError(ValueError):
    def __init__(self):
        super().__init__(
            "FR : revue humaine invalide. EN: invalid human review. ES: revisión humana no válida."
        )


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def record_digest(row):
    return digest(
        {
            "id": row.id,
            "text": row.text,
            "assigned": row.assigned,
            "probabilities": row.probabilities,
            "review": row.review,
            "request_id": row.request_id,
        }
    )


def validate_source(coded: CodedFile, codebook: Codebook):
    if coded.code_ids != codebook.code_ids or len(coded.ids) != len(coded.records):
        raise ReviewError()
    if any(
        not row.id
        or set(row.assigned) != set(coded.code_ids)
        or set(row.probabilities) != set(coded.code_ids)
        or any(value not in (0, 1) for value in row.assigned.values())
        or any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            or not 0 <= value <= 1
            for value in row.probabilities.values()
        )
        for row in coded.records
    ):
        raise ReviewError()


def export_review_queue(coded: CodedFile, codebook: Codebook, *, include_text=False):
    validate_source(coded, codebook)
    book_hash = digest(codebook.to_dict())
    rows = []
    for row in coded.records:
        if not row.review:
            continue
        item = {
            "id": row.id,
            "record_sha256": record_digest(row),
            "codebook_sha256": book_hash,
            "codes": None,
            "suggested_codes": [c for c in coded.code_ids if row.assigned.get(c)],
            "probabilities": dict(row.probabilities),
        }
        if include_text:
            item["text"] = row.text
        rows.append(item)
    return {"version": 1, "decisions": rows}


def apply_review_decisions(coded: CodedFile, codebook: Codebook, queue):
    validate_source(coded, codebook)
    if (
        not isinstance(queue, dict)
        or queue.get("version") != 1
        or not isinstance(queue.get("decisions"), list)
    ):
        raise ReviewError()
    originals = {row.id: row for row in coded.records}
    book_hash, seen, selected = digest(codebook.to_dict()), set(), []
    for decision in queue["decisions"]:
        if not isinstance(decision, dict):
            raise ReviewError()
        identifier = decision.get("id")
        if (
            not isinstance(identifier, str)
            or identifier in seen
            or identifier not in originals
        ):
            raise ReviewError()
        seen.add(identifier)
        row = originals[identifier]
        codes = decision.get("codes")
        if (
            not row.review
            or decision.get("record_sha256") != record_digest(row)
            or decision.get("codebook_sha256") != book_hash
        ):
            raise ReviewError()
        if (
            not isinstance(codes, list)
            or any(not isinstance(c, str) or c not in coded.code_ids for c in codes)
            or len(set(codes)) != len(codes)
        ):
            raise ReviewError()
        if codebook.mode == "single" and len(codes) > 1:
            raise ReviewError()
        if "text" in decision and decision["text"] != row.text:
            raise ReviewError()
        selected.append((row, set(codes)))
    result = copy.deepcopy(coded)
    targets = {row.id: row for row in result.records}
    changes = []
    for source, codes in selected:
        target = targets[source.id]
        target.assigned = {c: int(c in codes) for c in coded.code_ids}
        target.review = False
        changes.append(
            {
                "id": source.id,
                "source_record_sha256": record_digest(source),
                "before_assigned": dict(source.assigned),
                "after_assigned": dict(target.assigned),
                "origin": "human_review",
            }
        )
    audit = {
        "version": 1,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "codebook_sha256": book_hash,
        "changes": changes,
        "model_probabilities_changed": False,
    }
    return result, audit


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ReviewError()

    def format_help(self):
        return super().format_help().replace("usage:", self.words["usage"] + ":", 1)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    lang = "en"
    for i, value in enumerate(argv):
        if value == "--lang" and i + 1 < len(argv):
            lang = argv[i + 1]
        elif value.startswith("--lang="):
            lang = value.split("=", 1)[1]
    lang = lang if lang in TEXT else "en"
    words = TEXT[lang]
    parser = Parser(description=words["title"], add_help=False)
    parser.words = words
    parser._action_groups[0].title = words["positional"]
    parser._action_groups[1].title = words["options"]
    parser.add_argument("-h", "--help", action="help", help=words["help"])
    parser.add_argument("command", choices=("export", "apply"))
    parser.add_argument("source", type=Path, help=words["source"])
    parser.add_argument("--codebook", required=True, type=Path, help=words["book"])
    parser.add_argument("--out", required=True, type=Path, help=words["out"])
    parser.add_argument("--decisions", type=Path, help=words["decisions"])
    parser.add_argument("--audit", type=Path, help=words["audit"])
    parser.add_argument("--include-text", action="store_true", help=words["include"])
    parser.add_argument("--lang", choices=TEXT, default=lang, help=words["lang"])
    created = []
    try:
        args = parser.parse_args(argv)
        if args.source.stat().st_size > 10_000_000:
            raise ReviewError()
        source_text = args.source.read_text(encoding="utf-8-sig")
        coded = read_coded(str(args.source))
        if source_text != args.source.read_text(encoding="utf-8-sig"):
            raise ReviewError()
        codebook = load_codebook(str(args.codebook))
        if args.command == "export":
            if args.audit or args.decisions:
                raise ReviewError()
            output = export_review_queue(
                coded, codebook, include_text=args.include_text
            )
            audit = None
        else:
            if (
                args.decisions is None
                or args.audit is None
                or args.include_text
                or args.audit.resolve() == args.out.resolve()
            ):
                raise ReviewError()
            if args.decisions.stat().st_size > 10_000_000:
                raise ReviewError()
            queue = json.loads(args.decisions.read_text(encoding="utf-8"))
            output, audit = apply_review_decisions(coded, codebook, queue)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(args.out, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        created.append(args.out)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            if args.command == "export":
                json.dump(output, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write("\n")
        if args.command == "apply":
            reader = csv.DictReader(io.StringIO(source_text, newline=""))
            if reader.fieldnames is None:
                raise ReviewError()
            changed = {row.id: row for row in output.records}
            reviewed_ids = {entry["id"] for entry in audit["changes"]}
            with open(args.out, "w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=reader.fieldnames)
                writer.writeheader()
                for original in reader:
                    row = changed[original["id"].strip()]
                    if row.id in reviewed_ids:
                        for code, assigned in row.assigned.items():
                            original[code] = str(assigned)
                        if "review" in original:
                            original["review"] = str(int(row.review))
                    writer.writerow(original)
            args.audit.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(args.audit, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            created.append(args.audit)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(audit, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write("\n")
        print(
            json.dumps(
                {
                    "message": words["saved"],
                    "files": [str(p) for p in created],
                    "scope": words["scope"],
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (
        OSError,
        ValueError,
        TypeError,
        AttributeError,
        RecursionError,
        KeyError,
        csv.Error,
    ):
        for path in created:
            path.unlink(missing_ok=True)
        print(words["invalid"], file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
