#!/usr/bin/env python3
import argparse
import os
import re
import sys


CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
MULTISPACE_RE = re.compile(r"[ \t]+")
PAGE_NUMBER_RE = re.compile(r"^\d{1,4}$")


def collect_txt_files(input_path):
    if os.path.isfile(input_path):
        return [input_path]

    txt_files = []
    for root, _, files in os.walk(input_path):
        for name in files:
            if name.lower().endswith(".txt"):
                txt_files.append(os.path.join(root, name))
    return txt_files


def resolve_output_root(input_path, output_path, in_place):
    if in_place:
        if os.path.isfile(input_path):
            return os.path.dirname(os.path.abspath(input_path))
        return os.path.abspath(input_path)
    if output_path == ".":
        if os.path.isfile(input_path):
            return os.path.dirname(os.path.abspath(input_path))
        return os.path.abspath(input_path)
    return os.path.abspath(output_path)


def normalize_lines(text, collapse_spaces, strip_page_numbers):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    text = text.replace("\t", " ")
    text = CONTROL_CHARS_RE.sub("", text)
    lines = text.split("\n")

    normalized = []
    for line in lines:
        if collapse_spaces:
            line = MULTISPACE_RE.sub(" ", line)
        line = line.strip()
        if strip_page_numbers and PAGE_NUMBER_RE.fullmatch(line or ""):
            continue
        normalized.append(line)
    return normalized


def collapse_blank_lines(lines, max_blank_lines):
    collapsed = []
    blank_count = 0
    for line in lines:
        if line == "":
            blank_count += 1
            if blank_count <= max_blank_lines:
                collapsed.append("")
        else:
            blank_count = 0
            collapsed.append(line)
    return trim_blank_edges(collapsed)


def trim_blank_edges(lines):
    start = 0
    end = len(lines)
    while start < end and lines[start] == "":
        start += 1
    while end > start and lines[end - 1] == "":
        end -= 1
    return lines[start:end]


def join_paragraph_lines(lines):
    if not lines:
        return ""
    combined = lines[0]
    for next_line in lines[1:]:
        if combined.endswith("-") and next_line and next_line[0].islower():
            combined = combined[:-1] + next_line
        else:
            if combined:
                combined += " "
            combined += next_line
    return combined


def unwrap_paragraphs(lines):
    unwrapped = []
    current = []
    for line in lines:
        if line == "":
            if current:
                unwrapped.append(join_paragraph_lines(current))
                current = []
            unwrapped.append("")
        else:
            current.append(line)
    if current:
        unwrapped.append(join_paragraph_lines(current))
    return trim_blank_edges(unwrapped)


def format_text(
    text,
    max_blank_lines=1,
    collapse_spaces=True,
    unwrap=False,
    strip_page_numbers=False,
):
    lines = normalize_lines(text, collapse_spaces, strip_page_numbers)
    lines = collapse_blank_lines(lines, max_blank_lines)
    if unwrap:
        lines = unwrap_paragraphs(lines)
    return "\n".join(lines) + "\n"


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def run(input_path, output_path, in_place=False, overwrite=False, dry_run=False, max_blank_lines=1, keep_spaces=False, unwrap=False, strip_page_numbers=False):
    input_path = os.path.abspath(input_path)
    if not os.path.exists(input_path):
        print(f"Input path not found: {input_path}", file=sys.stderr)
        return 1

    txt_files = collect_txt_files(input_path)
    if not txt_files:
        print("No text files found.", file=sys.stderr)
        return 1

    output_root = resolve_output_root(input_path, output_path, in_place)
    input_root = (
        os.path.dirname(input_path) if os.path.isfile(input_path) else input_path
    )

    total = len(txt_files)
    written = 0
    skipped = 0
    failed = 0

    for index, path in enumerate(txt_files, 1):
        rel_path = os.path.relpath(path, input_root)
        out_path = os.path.join(output_root, rel_path)

        if not in_place and os.path.abspath(out_path) == os.path.abspath(path):
            if not overwrite:
                print(
                    f"[{index}/{total}] Output equals input, skipping: {rel_path}"
                )
                skipped += 1
                continue

        if os.path.exists(out_path) and not overwrite and not in_place:
            print(f"[{index}/{total}] Exists, skipping: {rel_path}")
            skipped += 1
            continue

        if dry_run:
            print(f"[{index}/{total}] Would write: {rel_path}")
            written += 1
            continue

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                raw_text = handle.read()
            formatted = format_text(
                raw_text,
                max_blank_lines=max(0, max_blank_lines),
                collapse_spaces=not keep_spaces,
                unwrap=unwrap,
                strip_page_numbers=strip_page_numbers,
            )
        except Exception as exc:
            print(f"[{index}/{total}] Failed: {rel_path} ({exc})", file=sys.stderr)
            failed += 1
            continue

        try:
            write_text(out_path, formatted)
        except Exception as exc:
            print(
                f"[{index}/{total}] Failed to write: {rel_path} ({exc})",
                file=sys.stderr,
            )
            failed += 1
            continue

        print(f"[{index}/{total}] Wrote: {rel_path}")
        written += 1

    print(
        f"Done. Processed {total} files. Wrote {written}, skipped {skipped}, failed {failed}."
    )
    return 0

def main():
    parser = argparse.ArgumentParser(
        description="Format text files by normalizing whitespace and paragraphs."
    )
    parser.add_argument(
        "--input",
        default="txt",
        help="Input text file or directory (default: txt)",
    )
    parser.add_argument(
        "--output",
        default="txt_formatted",
        help="Output directory (default: txt_formatted, use '.' to write alongside)",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Overwrite files in place",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be formatted without writing files",
    )
    parser.add_argument(
        "--max-blank-lines",
        type=int,
        default=1,
        help="Max consecutive blank lines to keep (default: 1)",
    )
    parser.add_argument(
        "--keep-spaces",
        action="store_true",
        help="Do not collapse multiple spaces into one",
    )
    parser.add_argument(
        "--unwrap",
        action="store_true",
        help="Join wrapped lines into paragraphs",
    )
    parser.add_argument(
        "--strip-page-numbers",
        action="store_true",
        help="Remove lines that contain only page numbers",
    )
    args = parser.parse_args()

    return run(args.input, args.output, args.in_place, args.overwrite, args.dry_run, args.max_blank_lines, args.keep_spaces, args.unwrap, args.strip_page_numbers)


if __name__ == "__main__":
    raise SystemExit(main())
