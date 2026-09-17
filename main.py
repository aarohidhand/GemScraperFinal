# ============================================================
# 09_main.py
#
# END-TO-END GeM RESEARCH DATA PIPELINE
#
# Stages:
#
#   01 → document resolution
#   02 → PDF download + text extraction
#   06 → Qwen constraint extraction
#   07 → deterministic normalization
#   08 → validation
#   09 → dataset export
#
# THIS IS THE ONLY SCRIPT THAT SHOULD BE RUN.
#
# 01 and 02 are invoked only when required.
# ============================================================

import csv
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from openai import OpenAI


# ============================================================
# CONFIG
# ============================================================

OUTPUT_ROOT = Path(
    "gem_pipeline_data"
)

METADATA_CSV = Path(
    "gem_bids_metadata.csv"
)

RESOLVER_SCRIPT = Path(
    "01_resolve_documents.py"
)

EXTRACTOR_SCRIPT = Path(
    "02_download_extract.py"
)


# ============================================================
# PIPELINE SWITCHES
# ============================================================

# ------------------------------------------------------------
# Number of BIDs
#
# 10   = current test
# None = all 2019+ BIDs
# ------------------------------------------------------------

MAX_BIDS = 10


# ------------------------------------------------------------
# Automatically run missing upstream data
#
# True:
#   If 01/02 data does not exist, create it.
#
# False:
#   Fail instead of automatically creating it.
# ------------------------------------------------------------

RUN_UPSTREAM_IF_MISSING = True


# ------------------------------------------------------------
# FORCE REDO
#
# False:
#   Reuse existing 01/02 outputs.
#
# True:
#   Rebuild 01 + 02 from scratch.
#   Also rerun 06-09.
# ------------------------------------------------------------

FORCE_REDO = False


# ------------------------------------------------------------
# DOWNSTREAM SWITCHES
#
# These allow development/testing of individual stages.
# ------------------------------------------------------------

RUN_QWEN = True

RUN_NORMALIZATION = True

RUN_VALIDATION = True

RUN_EXPORT = True


# ============================================================
# QWEN CONFIG
# ============================================================

# IMPORTANT:
#
# Do not invent an API endpoint here.
#
# Put the actual Qwen provider configuration here once
# you decide whether this is:
#
#   - local Qwen
#   - Ollama
#   - vLLM
#   - DashScope
#   - OpenAI-compatible provider
#
# ------------------------------------------------------------

# ============================================================
# QWEN / vLLM CONFIG
# ============================================================

# ============================================================
# QWEN / vLLM CONFIG
# ============================================================

QWEN_MODEL = (
    "JunHowie/Qwen3-8B-GPTQ-Int4"
)

QWEN_BASE_URL = (
    "http://localhost:8000/v1"
)

QWEN_API_KEY = "EMPTY"

QWEN_TEMPERATURE = 0.0

QWEN_MAX_TOKENS = 4096

qwen_client = OpenAI(
    base_url=QWEN_BASE_URL,
    api_key=QWEN_API_KEY,
)


# ============================================================
# OUTPUT FILES
# ============================================================

RAW_CONSTRAINTS_FILE = (
    OUTPUT_ROOT
    / "bid_constraints_raw.jsonl"
)

NORMALIZED_CONSTRAINTS_FILE = (
    OUTPUT_ROOT
    / "bid_constraints.jsonl"
)

VALIDATION_FILE = (
    OUTPUT_ROOT
    / "constraint_validation.jsonl"
)

FINAL_DATASET_FILE = (
    OUTPUT_ROOT
    / "bid_constraints.csv"
)


# ============================================================
# QWEN EXTRACTION SCHEMA
# ============================================================

CONSTRAINT_SCHEMA = {
    "bid_id": "",
    "bid_number": "",
    "constraints": [
        {
            "source": "",
            "constraint_type": "",
            "attribute": "",
            "operator": "",
            "value": "",
            "unit": "",
            "hard_soft": "",
            "confidence": 0.0,
            "raw_text": "",
            "page": None,
        }
    ],
}


# ============================================================
# DOCUMENT ROLES USED BY QWEN
# ============================================================

QWEN_SOURCE_ROLES = {
    "BID",
    "TECHNICAL_SPEC",
    "BOQ",
    "ATC",
    "CORRIGENDUM",
    "ELIGIBILITY",
}


# RA IS DELIBERATELY EXCLUDED.
#
# RA documents are retained for provenance but normally point
# back to the parent BID and should not create duplicate
# constraints.
# ============================================================


# ============================================================
# UTILITY
# ============================================================

def max_bids_args():

    if MAX_BIDS is None:
        return []

    return [
        "--max-bids",
        str(MAX_BIDS),
    ]


def get_manifests():

    manifests = sorted(
        OUTPUT_ROOT.glob(
            "*/resolved_documents.json"
        )
    )

    if MAX_BIDS is not None:
        manifests = manifests[:MAX_BIDS]

    return manifests


# ============================================================
# RUN STAGE 01
# ============================================================

def run_stage_01():

    print("\n")
    print("=" * 90)
    print("STAGE 01 — DOCUMENT RESOLUTION")
    print("=" * 90)

    command = [
        sys.executable,
        str(RESOLVER_SCRIPT),
        *max_bids_args(),
    ]

    result = subprocess.run(
        command,
        check=False,
    )

    if result.returncode != 0:

        raise RuntimeError(
            "Stage 01 failed."
        )


# ============================================================
# CHECK STAGE 01
# ============================================================

def stage_01_exists():

    manifests = get_manifests()

    if not manifests:
        return False

    if MAX_BIDS is None:
        return True

    return len(manifests) >= MAX_BIDS


# ============================================================
# CHECK STAGE 02
# ============================================================

def bid_extraction_complete(
    manifest_path
):

    status_path = (
        manifest_path.parent
        / "pipeline_status.json"
    )

    if not status_path.exists():
        return False

    try:

        status = json.loads(
            status_path.read_text(
                encoding="utf-8"
            )
        )

    except Exception:

        return False

    documents = status.get(
        "documents",
        [],
    )

    if not documents:
        return False

    for document in documents:

        status_value = document.get(
            "status",
            "",
        )

        if status_value == (
            "SKIPPED_PRODUCT_CATALOGUE"
        ):
            continue

        if "FAILED" in status_value:
            return False

        text_path = document.get(
            "text_path"
        )

        if not text_path:
            return False

        if not Path(
            text_path
        ).exists():

            return False

    return True


def stage_02_exists():

    manifests = get_manifests()

    if not manifests:
        return False

    return all(
        bid_extraction_complete(
            manifest
        )
        for manifest in manifests
    )


# ============================================================
# RUN STAGE 02
# ============================================================

def run_stage_02(
    force=False
):

    print("\n")
    print("=" * 90)
    print("STAGE 02 — DOWNLOAD + TEXT EXTRACTION")
    print("=" * 90)

    command = [
        sys.executable,
        str(EXTRACTOR_SCRIPT),
        *max_bids_args(),
    ]

    if force:

        command.append(
            "--force"
        )

    result = subprocess.run(
        command,
        check=False,
    )

    if result.returncode != 0:

        raise RuntimeError(
            "Stage 02 failed."
        )


# ============================================================
# ENSURE UPSTREAM DATA
# ============================================================

def ensure_upstream():

    # --------------------------------------------------------
    # FORCE
    # --------------------------------------------------------

    if FORCE_REDO:

        print("\n")
        print(
            "FORCE_REDO=True"
        )

        print(
            "Rebuilding stages 01 and 02."
        )

        run_stage_01()

        run_stage_02(
            force=True
        )

        return


    # --------------------------------------------------------
    # STAGE 01
    # --------------------------------------------------------

    if stage_01_exists():

        print(
            "\nSTAGE 01:"
            " existing resolution found."
            " Skipping."
        )

    else:

        if not RUN_UPSTREAM_IF_MISSING:

            raise RuntimeError(
                "Stage 01 data is missing "
                "and RUN_UPSTREAM_IF_MISSING=False."
            )

        print(
            "\nSTAGE 01:"
            " resolution missing."
            " Running."
        )

        run_stage_01()


    # --------------------------------------------------------
    # STAGE 02
    # --------------------------------------------------------

    if stage_02_exists():

        print(
            "\nSTAGE 02:"
            " existing extraction found."
            " Skipping."
        )

    else:

        if not RUN_UPSTREAM_IF_MISSING:

            raise RuntimeError(
                "Stage 02 data is missing "
                "and RUN_UPSTREAM_IF_MISSING=False."
            )

        print(
            "\nSTAGE 02:"
            " extraction missing/incomplete."
            " Running."
        )

        run_stage_02()


# ============================================================
# DOCUMENT LOADING
# ============================================================

def load_documents():

    manifests = get_manifests()

    records = []

    for manifest_path in manifests:

        manifest = json.loads(
            manifest_path.read_text(
                encoding="utf-8"
            )
        )

        bid_documents = []

        for document in manifest.get(
            "documents",
            [],
        ):

            role = document.get(
                "role",
                "OTHER",
            )

            # ------------------------------------------------
            # RA deliberately excluded from extraction.
            # ------------------------------------------------

            if role == "RA":
                continue

            if role not in QWEN_SOURCE_ROLES:
                continue

            text_path = document.get(
                "text_path"
            )

            if not text_path:
                continue

            path = Path(
                text_path
            )

            if not path.exists():
                continue

            text = path.read_text(
                encoding="utf-8",
                errors="replace",
            )

            bid_documents.append({
                "role": role,
                "path": str(path),
                "text": text,
            })

        records.append({
            "bid_id": manifest.get(
                "bid_id"
            ),
            "bid_number": manifest.get(
                "bid_number"
            ),
            "documents": bid_documents,
        })

    return records


# ============================================================
# QWEN PROMPT
# ============================================================

def build_qwen_prompt(
    bid,
):

    documents = []

    for document in bid[
        "documents"
    ]:

        documents.append(
            "\n".join([
                "=" * 70,
                f"SOURCE ROLE: {document['role']}",
                f"SOURCE FILE: {document['path']}",
                "=" * 70,
                document["text"],
            ])
        )

    combined_text = "\n\n".join(
        documents
    )

    return f"""
You are extracting procurement constraints from a GeM
procurement document.

BID NUMBER:
{bid["bid_number"]}

BID ID:
{bid["bid_id"]}

Extract only constraints explicitly supported by the
provided documents.

Constraint types:

- product
- certification
- delivery
- experience
- licence
- geography
- price
- quantity
- supplier_eligibility

Operators:

- =
- >=
- <=
- in
- required

For every constraint provide:

- source
- page
- constraint_type
- attribute
- operator
- value
- unit
- hard_soft
- confidence
- raw_text

Rules:

1. Do not invent constraints.
2. Do not infer values not present in the text.
3. Preserve the exact evidence sentence in raw_text.
4. Preserve page number where identifiable.
5. Distinguish product constraints from supplier constraints.
6. Mark mandatory/required conditions as hard.
7. Mark preferences or non-mandatory conditions as soft.
8. If hardness is unclear, use "unknown".
9. Do not treat the RA as a separate constraint source.
10. Do not summarize the document.
11. Extract atomic constraints rather than large combined
    paragraphs.
12. Return valid JSON only.

DOCUMENTS:

{combined_text}
"""

# ============================================================
# QWEN CALL
# ============================================================


def call_qwen(prompt):

    response = (
        qwen_client
        .chat
        .completions
        .create(
            model=QWEN_MODEL,

            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],

            temperature=0,

            max_tokens=4096,
        )
    )

    content = (
        response
        .choices[0]
        .message
        .content
    )

    if not content:
        raise RuntimeError(
            "Qwen returned empty response."
        )

    return content

# ============================================================
# STAGE 06
# ============================================================

def run_qwen_extraction(
    records
):

    print("\n")
    print("=" * 90)
    print("STAGE 06 — QWEN CONSTRAINT EXTRACTION")
    print("=" * 90)

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    with RAW_CONSTRAINTS_FILE.open(
        "w",
        encoding="utf-8",
    ) as output:

        for index, bid in enumerate(
            records,
            start=1,
        ):

            print(
                f"\n[{index}/{len(records)}] "
                f"{bid['bid_number']}"
            )

            prompt = build_qwen_prompt(
                bid
            )

            try:

                result = call_qwen(
                    prompt
                )

                if isinstance(
                    result,
                    str,
                ):

                    result = json.loads(
                        result
                    )

                record = {
                    "bid_id":
                        bid["bid_id"],
                    "bid_number":
                        bid["bid_number"],
                    "constraints":
                        result.get(
                            "constraints",
                            [],
                        ),
                }

                output.write(
                    json.dumps(
                        record,
                        ensure_ascii=False,
                    )
                    + "\n"
                )

            except Exception as e:

                raise RuntimeError(
                    f"Qwen extraction failed for "
                    f"{bid['bid_number']}: {e}"
                ) from e

            time.sleep(
                0.5
            )


# ============================================================
# NORMALIZATION
# ============================================================

OPERATOR_MAP = {
    "minimum": ">=",
    "min": ">=",
    "at least": ">=",
    "maximum": "<=",
    "max": "<=",
    "up to": "<=",
    "mandatory": "required",
    "required": "required",
    "must": "required",
}


ATTRIBUTE_MAP = {
    "delivery period":
        "delivery_days",

    "delivery time":
        "delivery_days",

    "delivery":
        "delivery_days",

    "minimum quantity":
        "quantity",

    "minimum order quantity":
        "quantity",

    "iso 9001":
        "iso_9001",

    "iso9001":
        "iso_9001",
}


def normalize_operator(
    value
):

    if not value:
        return value

    value = str(
        value
    ).strip().lower()

    return OPERATOR_MAP.get(
        value,
        value,
    )


def normalize_attribute(
    value
):

    if not value:
        return value

    original = str(
        value
    ).strip()

    lookup = original.lower()

    return ATTRIBUTE_MAP.get(
        lookup,
        original,
    )


def normalize_constraint(
    constraint
):

    normalized = dict(
        constraint
    )

    normalized[
        "operator"
    ] = normalize_operator(
        constraint.get(
            "operator"
        )
    )

    normalized[
        "attribute"
    ] = normalize_attribute(
        constraint.get(
            "attribute"
        )
    )

    return normalized


# ============================================================
# STAGE 07
# ============================================================

def run_normalization():

    print("\n")
    print("=" * 90)
    print("STAGE 07 — CONSTRAINT NORMALIZATION")
    print("=" * 90)

    if not RAW_CONSTRAINTS_FILE.exists():

        raise RuntimeError(
            "Raw Qwen constraint file does not exist."
        )

    with (
        RAW_CONSTRAINTS_FILE.open(
            "r",
            encoding="utf-8",
        ) as source,
        NORMALIZED_CONSTRAINTS_FILE.open(
            "w",
            encoding="utf-8",
        ) as target
    ):

        for line in source:

            if not line.strip():
                continue

            record = json.loads(
                line
            )

            normalized = []

            for constraint in record.get(
                "constraints",
                [],
            ):

                normalized.append(
                    normalize_constraint(
                        constraint
                    )
                )

            record[
                "constraints"
            ] = normalized

            target.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                )
                + "\n"
            )


# ============================================================
# VALIDATION
# ============================================================

VALID_OPERATORS = {
    "=",
    ">=",
    "<=",
    "in",
    "required",
}


def validate_constraint(
    constraint,
    source_text,
):

    errors = []

    required_fields = [
        "source",
        "constraint_type",
        "attribute",
        "operator",
        "value",
        "hard_soft",
        "confidence",
        "raw_text",
    ]

    for field in required_fields:

        if field not in constraint:

            errors.append(
                f"missing:{field}"
            )

    operator = constraint.get(
        "operator"
    )

    if operator not in VALID_OPERATORS:

        errors.append(
            f"invalid_operator:{operator}"
        )

    raw_text = str(
        constraint.get(
            "raw_text",
            ""
        )
    ).strip()

    # --------------------------------------------------------
    # Evidence validation
    # --------------------------------------------------------

    if not raw_text:

        errors.append(
            "missing_evidence"
        )

    else:

        normalized_source = re.sub(
            r"\s+",
            " ",
            source_text.lower(),
        )

        normalized_evidence = re.sub(
            r"\s+",
            " ",
            raw_text.lower(),
        )

        if normalized_evidence not in normalized_source:

            errors.append(
                "evidence_not_found"
            )

    # --------------------------------------------------------
    # Confidence
    # --------------------------------------------------------

    confidence = constraint.get(
        "confidence"
    )

    try:

        confidence = float(
            confidence
        )

        if not 0 <= confidence <= 1:

            errors.append(
                "confidence_out_of_range"
            )

    except Exception:

        errors.append(
            "invalid_confidence"
        )

    return {
        "valid":
            len(errors) == 0,
        "errors":
            errors,
    }


# ============================================================
# STAGE 08
# ============================================================

def run_validation():

    print("\n")
    print("=" * 90)
    print("STAGE 08 — CONSTRAINT VALIDATION")
    print("=" * 90)

    if not NORMALIZED_CONSTRAINTS_FILE.exists():

        raise RuntimeError(
            "Normalized constraints do not exist."
        )

    records = []

    with NORMALIZED_CONSTRAINTS_FILE.open(
        "r",
        encoding="utf-8",
    ) as source:

        for line in source:

            if line.strip():

                records.append(
                    json.loads(
                        line
                    )
                )

    # --------------------------------------------------------
    # Build source text lookup
    # --------------------------------------------------------

    source_records = {}

    for bid in load_documents():

        source_records[
            bid["bid_number"]
        ] = bid

    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    with VALIDATION_FILE.open(
        "w",
        encoding="utf-8",
    ) as output:

        for record in records:

            bid_number = record[
                "bid_number"
            ]

            bid_source = source_records.get(
                bid_number
            )

            source_text = ""

            if bid_source:

                source_text = "\n".join(
                    document["text"]
                    for document
                    in bid_source[
                        "documents"
                    ]
                )

            validated_constraints = []

            for constraint in record.get(
                "constraints",
                [],
            ):

                validation = (
                    validate_constraint(
                        constraint,
                        source_text,
                    )
                )

                validated_constraints.append({
                    **constraint,
                    "validation":
                        validation,
                })

            output.write(
                json.dumps(
                    {
                        "bid_id":
                            record["bid_id"],
                        "bid_number":
                            bid_number,
                        "constraints":
                            validated_constraints,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


# ============================================================
# STAGE 09 EXPORT
# ============================================================

def run_export():

    print("\n")
    print("=" * 90)
    print("STAGE 09 — DATASET EXPORT")
    print("=" * 90)

    if not VALIDATION_FILE.exists():

        raise RuntimeError(
            "Validation file does not exist."
        )

    rows = []

    with VALIDATION_FILE.open(
        "r",
        encoding="utf-8",
    ) as source:

        for line in source:

            if not line.strip():
                continue

            record = json.loads(
                line
            )

            for index, constraint in enumerate(
                record.get(
                    "constraints",
                    [],
                ),
                start=1,
            ):

                validation = constraint.get(
                    "validation",
                    {},
                )

                rows.append({
                    "bid_id":
                        record["bid_id"],

                    "bid_number":
                        record["bid_number"],

                    "constraint_id":
                        (
                            f"{record['bid_id']}"
                            f"_{index}"
                        ),

                    "source":
                        constraint.get(
                            "source",
                            "",
                        ),

                    "constraint_type":
                        constraint.get(
                            "constraint_type",
                            "",
                        ),

                    "attribute":
                        constraint.get(
                            "attribute",
                            "",
                        ),

                    "operator":
                        constraint.get(
                            "operator",
                            "",
                        ),

                    "value":
                        constraint.get(
                            "value",
                            "",
                        ),

                    "unit":
                        constraint.get(
                            "unit",
                            "",
                        ),

                    "hard_soft":
                        constraint.get(
                            "hard_soft",
                            "",
                        ),

                    "confidence":
                        constraint.get(
                            "confidence",
                            "",
                        ),

                    "raw_text":
                        constraint.get(
                            "raw_text",
                            "",
                        ),

                    "page":
                        constraint.get(
                            "page",
                            "",
                        ),

                    "valid":
                        validation.get(
                            "valid",
                            False,
                        ),

                    "validation_errors":
                        "|".join(
                            validation.get(
                                "errors",
                                [],
                            )
                        ),
                })

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    fieldnames = [
        "bid_id",
        "bid_number",
        "constraint_id",
        "source",
        "constraint_type",
        "attribute",
        "operator",
        "value",
        "unit",
        "hard_soft",
        "confidence",
        "raw_text",
        "page",
        "valid",
        "validation_errors",
    ]

    with FINAL_DATASET_FILE.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as output:

        writer = csv.DictWriter(
            output,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        writer.writerows(
            rows
        )

    print(
        f"\nExported "
        f"{len(rows)} constraints."
    )

    print(
        f"Dataset:\n"
        f"{FINAL_DATASET_FILE.resolve()}"
    )


# ============================================================
# PIPELINE
# ============================================================

def main():

    print("\n")
    print("=" * 100)
    print("GeM END-TO-END RESEARCH PIPELINE")
    print("=" * 100)

    print(
        f"""
MAX_BIDS                = {MAX_BIDS}

RUN_UPSTREAM_IF_MISSING = {RUN_UPSTREAM_IF_MISSING}
FORCE_REDO              = {FORCE_REDO}

RUN_QWEN                = {RUN_QWEN}
RUN_NORMALIZATION       = {RUN_NORMALIZATION}
RUN_VALIDATION          = {RUN_VALIDATION}
RUN_EXPORT              = {RUN_EXPORT}
"""
    )

    # ========================================================
    # 01 + 02
    # ========================================================

    ensure_upstream()

    # ========================================================
    # Load extracted documents
    # ========================================================

    records = load_documents()

    print(
        f"\nLoaded "
        f"{len(records)} BIDs "
        f"for constraint extraction."
    )

    # ========================================================
    # 06
    # ========================================================

    if RUN_QWEN:

        run_qwen_extraction(
            records
        )

    # ========================================================
    # 07
    # ========================================================

    if RUN_NORMALIZATION:

        run_normalization()

    # ========================================================
    # 08
    # ========================================================

    if RUN_VALIDATION:

        run_validation()

    # ========================================================
    # 09
    # ========================================================

    if RUN_EXPORT:

        run_export()

    # ========================================================
    # COMPLETE
    # ========================================================

    print("\n")
    print("=" * 100)
    print("END-TO-END PIPELINE COMPLETE")
    print("=" * 100)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print(
            "\nPipeline interrupted."
        )

        sys.exit(130)

    except Exception as e:

        print(
            "\nPIPELINE FAILED:"
        )

        print(e)

        sys.exit(1)