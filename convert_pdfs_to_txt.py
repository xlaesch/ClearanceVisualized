#!/usr/bin/env python3
import argparse
import os
import sys


def is_pdf_file(path):
    try:
        with open(path, "rb") as handle:
            return handle.read(5) == b"%PDF-"
    except OSError:
        return False


def extract_text_from_pdf(path):
    try:
        from pypdf import PdfReader
    except Exception as exc:
        raise RuntimeError(
            "Missing dependency: pypdf. Install with: python -m pip install pypdf"
        ) from exc

    reader = PdfReader(path)
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:
            raise RuntimeError(f"Encrypted PDF: {path}") from exc

    parts = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text:
            parts.append(text)
    return "\n".join(parts)


def collect_pdf_files(input_path):
    if os.path.isfile(input_path):
        return [input_path]

    pdf_files = []
    for root, _, files in os.walk(input_path):
        for name in files:
            if name.lower().endswith(".pdf"):
                pdf_files.append(os.path.join(root, name))
    return pdf_files


def resolve_output_root(input_path, output_path):
    if output_path == ".":
        if os.path.isfile(input_path):
            return os.path.dirname(os.path.abspath(input_path))
        return os.path.abspath(input_path)
    return os.path.abspath(output_path)


def main():
    parser = argparse.ArgumentParser(
        description="Convert PDF files to text files using pypdf."
    )
    parser.add_argument(
        "--input",
        default="pdfs",
        help="Input PDF file or directory (default: pdfs)",
    )
    parser.add_argument(
        "--output",
        default="txt",
        help="Output directory (default: txt, use '.' for alongside PDFs)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing text files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be converted without writing files",
    )
    args = parser.parse_args()

    input_path = os.path.abspath(args.input)
    if not os.path.exists(input_path):
        print(f"Input path not found: {input_path}", file=sys.stderr)
        return 1

    pdf_files = collect_pdf_files(input_path)
    if not pdf_files:
        print("No PDF files found.", file=sys.stderr)
        return 1

    output_root = resolve_output_root(input_path, args.output)
    input_root = (
        os.path.dirname(input_path) if os.path.isfile(input_path) else input_path
    )

    total = len(pdf_files)
    written = 0
    skipped = 0
    failed = 0

    for index, path in enumerate(pdf_files, 1):
        rel_path = os.path.relpath(path, input_root)
        rel_no_ext = os.path.splitext(rel_path)[0] + ".txt"
        out_path = os.path.join(output_root, rel_no_ext)

        if not is_pdf_file(path):
            print(f"[{index}/{total}] Skipping non-PDF: {rel_path}")
            skipped += 1
            continue

        if os.path.exists(out_path) and not args.overwrite:
            print(f"[{index}/{total}] Exists, skipping: {rel_no_ext}")
            skipped += 1
            continue

        if args.dry_run:
            print(f"[{index}/{total}] Would write: {rel_no_ext}")
            written += 1
            continue

        try:
            text = extract_text_from_pdf(path)
        except Exception as exc:
            print(f"[{index}/{total}] Failed: {rel_path} ({exc})", file=sys.stderr)
            failed += 1
            continue

        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        print(f"[{index}/{total}] Wrote: {rel_no_ext}")
        written += 1

    print(
        f"Done. Processed {total} PDFs. Wrote {written}, skipped {skipped}, failed {failed}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
