#!/usr/bin/env python3
import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request


def load_dotenv():
    candidates = []
    explicit = os.environ.get("DOTENV_PATH")
    if explicit:
        candidates.append(explicit)
    candidates.append(".env")
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

    for path in candidates:
        if not path or not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("export "):
                        line = line[len("export ") :].strip()
                    if "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    if not key:
                        continue
                    if (
                        len(value) >= 2
                        and value[0] == value[-1]
                        and value[0] in {"'", '"'}
                    ):
                        value = value[1:-1]
                    # Always overwrite with .env values to ensure fresh configuration
                    os.environ[key] = value
            return
        except OSError:
            continue


load_dotenv()

TAXONOMY = {
    "Drugs": [
        "Use during clearance process",
        "Use after submitting SF-86",
        "Recent use within adjudicative window",
        "Pattern of recurring use",
        "Distribution or intent to distribute",
        "Failure to disclose use",
        "Use of federally illegal substances despite state legality",
        "Association with drug users or dealers",
    ],
    "Financial": [
        "Unpaid taxes",
        "Chronic delinquent debt",
        "Bankruptcy with aggravating factors",
        "Gambling-related losses",
        "Unexplained affluence",
        "Failure to file required financial disclosures",
        "Ongoing collection actions or judgments",
    ],
    "Criminal Conduct": [
        "Felony conviction",
        "Misdemeanor pattern",
        "Recent arrest without conviction",
        "Probation or parole status",
        "Failure to disclose prior charges",
        "Violent conduct",
        "Weapons-related offenses",
    ],
    "Personal Conduct": [
        "False statements on SF-86",
        "Omission of required information",
        "Pattern of dishonesty",
        "Misrepresentation during interviews",
        "Prior employment misconduct",
        "Security violations in past roles",
    ],
    "Foreign Influence": [
        "Immediate family members who are foreign nationals",
        "Close and continuing foreign contacts",
        "Financial ties to foreign persons or entities",
        "Foreign business interests",
        "Travel with undeclared foreign contacts",
        "Failure to report foreign relationships",
    ],
    "Foreign Preference": [
        "Use of foreign passport",
        "Military service for a foreign country",
        "Voting in foreign elections",
        "Preference shown in official actions",
        "Refusal or delay in renouncing foreign citizenship",
    ],
    "Alcohol Consumption": [
        "DUI or DWI incidents",
        "Alcohol-related criminal conduct",
        "Pattern of binge drinking",
        "Use affecting work performance",
        "Failure to disclose treatment or incidents",
    ],
    "Psychological Conditions": [
        "Condition affecting judgment or reliability",
        "Failure to follow prescribed treatment",
        "Recent hospitalization with security impact",
        "Dishonesty about diagnosis or treatment",
        "Noncompliance with medical recommendations",
    ],
    "Technology Misuse / Information Security": [
        "Unauthorized access to systems",
        "Mishandling classified or sensitive data",
        "Policy violations involving IT systems",
        "Use of prohibited software or devices",
        "Prior insider-threat indicators",
    ],
}


DEFAULT_ENDPOINT = os.environ.get(
    "LLM_ENDPOINT", "https://api.openai.com/v1/chat/completions"
)
DEFAULT_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")


def build_prompt(case_text):
    taxonomy_json = json.dumps(TAXONOMY, indent=2)
    system = (
        "You are a classification assistant for security clearance cases.\n"
        "Return ONLY a JSON object with these keys:\n"
        "category_level_1, category_level_2, insights, notes, status\n"
        "- category_level_1 must be one of the Level 1 keys in the taxonomy.\n"
        "- category_level_2 must be one of the Level 2 values for that Level 1.\n"
        "- insights must be a one-sentence insight/advice for current applicants based on this decision.\n"
        "- notes must be a brief ASCII-only summary (<=120 chars) or empty.\n"
        "- status must be either 'Passed' or 'Failed' based on the decision.\n"
        "No additional keys. No markdown."
    )
    user = (
        "Taxonomy (Level 1 -> Level 2):\n"
        f"{taxonomy_json}\n\n"
        "Case text:\n"
        "<<<\n"
        f"{case_text}\n"
        ">>>"
    )
    return system, user


def is_pdf_file(path):
    try:
        with open(path, "rb") as handle:
            header = handle.read(5)
        return header == b"%PDF-"
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


def load_text(path, allow_non_pdf):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        if not is_pdf_file(path):
            if allow_non_pdf:
                with open(path, "r", encoding="utf-8", errors="replace") as handle:
                    return handle.read(), "not_pdf"
            return "", "not_pdf"
        return extract_text_from_pdf(path), ""

    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read(), ""


def iter_case_files(input_path, extensions):
    if os.path.isfile(input_path):
        yield input_path
        return

    for root, _, files in os.walk(input_path):
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if extensions and ext not in extensions:
                continue
            yield os.path.join(root, name)


def call_llm(
    endpoint,
    api_key,
    model,
    system_prompt,
    user_prompt,
    timeout,
    use_response_format,
    max_tokens,
):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
    }
    if use_response_format:
        payload["response_format"] = {"type": "json_object"}

    data = json.dumps(payload).encode("utf-8")
    
    max_retries = 5
    for attempt in range(max_retries + 1):
        try:
            request = urllib.request.Request(endpoint, data=data, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
            decoded = json.loads(raw)
            content = decoded["choices"][0]["message"]["content"]
            return content
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                if attempt < max_retries:
                    # Exponential backoff: 2, 4, 8, 16, 32...
                    sleep_time = 2 ** (attempt + 1)
                    print(f"Rate limited (429). Retrying in {sleep_time}s...", file=sys.stderr)
                    time.sleep(sleep_time)
                    continue
            raise 


def extract_json(text):
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def validate_labels(level1, level2):
    if level1 in TAXONOMY and level2 in TAXONOMY[level1]:
        return level1, level2, ""

    if level2:
        for candidate_level1, options in TAXONOMY.items():
            if level2 in options:
                return candidate_level1, level2, "level1_corrected"

    return level1, level2, "invalid_label"


def parse_llm_output(content):
    parsed = json.loads(extract_json(content))
    return {
        "category_level_1": parsed.get("category_level_1", "").strip(),
        "category_level_2": parsed.get("category_level_2", "").strip(),
        "insights": parsed.get("insights", "").strip(),
        "notes": parsed.get("notes", "").strip(),
        "status": parsed.get("status", "").strip(),
    }


def normalize_confidence(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def run(argv=None):
    parser = argparse.ArgumentParser(
        description="Classify case texts using an LLM and write results to CSV."
    )
    parser.add_argument(
        "--input",
        default=None,
        help=(
            "Directory or file containing case PDFs or text files "
            "(default: txt_formatted if exists, else txt, else pdfs)"
        ),
    )
    parser.add_argument(
        "--output",
        default="classified_cases.csv",
        help="Output CSV path",
    )
    parser.add_argument(
        "--extensions",
        default=None,
        help=(
            "Comma-separated list of file extensions to include "
            "(default: .txt for txt/txt_formatted input, else .pdf,.txt)"
        ),
    )
    parser.add_argument(
        "--allow-non-pdf",
        action="store_true",
        help="Allow .pdf files that are not actual PDFs",
    )
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        help="LLM API endpoint (OpenAI compatible)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="LLM model name",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY"),
        help="LLM API key (or set LLM_API_KEY / OPENAI_API_KEY)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Network timeout in seconds",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=12000,
        help="Max characters of case text to send to the LLM",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=256,
        help="Max tokens for LLM output",
    )
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=0.7,
        help="Threshold to flag cases for human review",
    )
    parser.add_argument(
        "--no-response-format",
        action="store_true",
        help="Disable JSON response format hint",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of cases (0 means no limit)",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=2.0,
        help="Seconds to sleep between LLM calls",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Process inputs and show how many cases would be classified",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from existing CSV output, skipping already classified cases",
    )
    parser.add_argument(
        "--manifest",
        default="pdfs/manifest.json",
        help="Path to manifest JSON mapping filenames to URLs",
    )
    args = parser.parse_args(argv)

    if not args.input:
        if os.path.isdir("txt_formatted"):
            args.input = "txt_formatted"
        elif os.path.isdir("txt"):
            args.input = "txt"
        else:
            args.input = "pdfs"

    extensions = []
    if args.extensions is None:
        if os.path.isfile(args.input):
            ext = os.path.splitext(args.input)[1].lower()
            if ext:
                extensions = [ext]
        else:
            input_name = os.path.basename(os.path.normpath(args.input)).lower()
            if input_name in {"txt", "txt_formatted"}:
                extensions = [".txt"]
            else:
                extensions = [".pdf", ".txt"]
    elif args.extensions:
        extensions = [ext.strip().lower() for ext in args.extensions.split(",") if ext]

    files = list(iter_case_files(args.input, extensions))
    if not files:
        print("No input files found.", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"Found {len(files)} case files.")
        return 0

    if not args.api_key:
        print("Missing API key. Set LLM_API_KEY or OPENAI_API_KEY.", file=sys.stderr)
        return 1

    fieldnames = [
        "case_id",
        "url",
        "category_level_1",
        "category_level_2",
        "insights",
        "notes",
        "status",
    ]

    # Load manifest if available
    manifest = {}
    if args.manifest and os.path.isfile(args.manifest):
         try:
             with open(args.manifest, "r", encoding="utf-8") as mf:
                 manifest = json.load(mf)
             # Create a mapping from base filename (no ext) to URL for easier lookup
             # Assumes manifest keys are filenames like 'case.pdf'
             manifest = {os.path.splitext(k)[0]: v for k, v in manifest.items()}
         except Exception as e:
             print(f"Warning: Could not load manifest: {e}", file=sys.stderr)

    seen_ids = set()
    processed = 0

    mode = "w"
    write_header = True

    if args.resume and os.path.isfile(args.output):
        mode = "a"
        write_header = False
        print(f"Resuming from {args.output}...")
        try:
            with open(args.output, "r", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    if "case_id" in row:
                        seen_ids.add(row["case_id"])
            print(f"Loaded {len(seen_ids)} existing cases.")
        except Exception as exc:
            print(f"Error reading existing CSV: {exc}", file=sys.stderr)
            return 1

    with open(args.output, mode, newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()

        for path in files:
            if args.limit and processed >= args.limit:
                break

            base_case_id = os.path.splitext(os.path.basename(path))[0]
            
            # Resume logic: if strict match found, skip
            if args.resume and base_case_id in seen_ids:
                continue

            case_id = base_case_id
            if case_id in seen_ids:
                suffix = 2
                while f"{case_id}_{suffix}" in seen_ids:
                    suffix += 1
                case_id = f"{case_id}_{suffix}"
            seen_ids.add(case_id)

            try:
                raw_text, load_note = load_text(path, args.allow_non_pdf)
            except Exception as exc:
                writer.writerow(
                    {
                        "case_id": case_id,
                        "url": manifest.get(base_case_id, ""),
                        "category_level_1": "",
                        "category_level_2": "",
                        "insights": "",
                        "notes": f"load_error: {exc}",
                        "status": "",
                    }
                )
                processed += 1
                continue

            raw_text = raw_text.replace("\x00", "")
            llm_text = raw_text[: args.max_chars]
            system_prompt, user_prompt = build_prompt(llm_text)

            notes = []
            if load_note:
                notes.append(load_note)
            if not raw_text.strip():
                notes.append("empty_text")
                writer.writerow(
                    {
                        "url": manifest.get(base_case_id, ""),
                        "case_id": case_id,
                        "category_level_1": "",
                        "category_level_2": "",
                        "insights": "",
                        "notes": "; ".join(notes),
                        "status": "",
                    }
                )
                processed += 1
                continue

            try:
                content = call_llm(
                    args.endpoint,
                    args.api_key,
                    args.model,
                    system_prompt,
                    user_prompt,
                    args.timeout,
                    not args.no_response_format,
                    args.max_output_tokens,
                )
                parsed = parse_llm_output(content)
            except urllib.error.HTTPError as exc:
                err_msg = exc.read().decode("utf-8", errors="replace")
                print(f"[ERROR] HTTP {exc.code} for case {case_id}: {err_msg}", file=sys.stderr)
                writer.writerow(
                    {
                        "url": manifest.get(base_case_id, ""),
                        "category_level_1": "",
                        "category_level_2": "",
                        "insights": "",
                        "notes": f"llm_http_error: {exc.code}",
                        "status": "",
                    }
                )
                processed += 1
                continue
            except Exception as exc:
                writer.writerow(
                    {
                        "case_id": case_id,
                        "url": manifest.get(base_case_id, ""),
                        "category_level_1": "",
                        "category_level_2": "",
                        "insights": "",
                        "notes": f"llm_error: {exc}",
                        "status": "",
                    }
                )
                processed += 1
                continue

            level1, level2, label_note = validate_labels(
                parsed["category_level_1"], parsed["category_level_2"]
            )
            if label_note:
                notes.append(label_note)

            insights = parsed.get("insights", "")
            status = parsed.get("status", "")

            if parsed["notes"]:
                notes.insert(0, parsed["notes"])

            writer.writerow(
                {
                    "case_id": case_id,
                    "url": manifest.get(base_case_id, ""),
                    "category_level_1": level1,
                    "category_level_2": level2,
                    "insights": insights,
                    "notes": "; ".join(notes),
                    "status": status,
                }
            )
            processed += 1

            if args.sleep:
                time.sleep(args.sleep)

    print(f"Wrote {processed} cases to {args.output}")
    return 0

def main():
    sys.exit(run())

if __name__ == "__main__":
    main()
