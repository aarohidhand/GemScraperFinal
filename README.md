# GeM Pipeline — Main Usage Guide

This document describes the three scripts in the current GeM pipeline:

```text
01_resolve_documents.py
02_download_extract.py
09_main.py
```

`09_main.py` is the main entry point for normal end-to-end execution.

## 1. Pipeline Overview

```text
gem_bids_metadata.csv
        |
        v
01_resolve_documents.py
        |
        v
resolved_documents.json
        |
        v
02_download_extract.py
        |
        v
extracted/*.txt
        |
        v
09_main.py
        |
        +-- Stage 06: Qwen constraint extraction
        +-- Stage 07: normalization
        +-- Stage 08: validation
        +-- Stage 09: dataset export
```

Important orchestration rule:

> `02_download_extract.py` does not call `01_resolve_documents.py`.

`09_main.py` decides whether stages 01 and 02 need to run.

This prevents document resolution from being repeated every time the downstream
Qwen/normalization/validation pipeline is run.

---

## 2. Files and Responsibilities

### 2.1 `01_resolve_documents.py`

Responsible for:

- reading `gem_bids_metadata.csv`
- selecting BIDs to process
- resolving document URLs
- identifying document roles
- creating one pipeline directory per BID
- writing `resolved_documents.json`

It does not download or extract PDFs.

Typical output:

```text
gem_pipeline_data/
└── GEM_2019_B_175334/
    └── resolved_documents.json
```

### 2.2 `02_download_extract.py`

Responsible for:

- reading existing `resolved_documents.json`
- downloading resolved PDF documents
- extracting native PDF text
- falling back to `pdfplumber`
- falling back to OCR when necessary
- saving extracted text
- deleting PDFs after successful extraction
- writing `pipeline_status.json`

It does not run stage 01.

Typical output:

```text
gem_pipeline_data/
└── GEM_2019_B_175334/
    ├── resolved_documents.json
    ├── pipeline_status.json
    ├── downloaded/
    └── extracted/
        ├── 00_BID.txt
        └── 01_RA.txt
```

The `downloaded/` directory is normally empty after successful extraction because
the PDF is deleted after the text has been successfully saved.

If extraction fails, the PDF is retained for debugging.

### 2.3 `09_main.py`

This is the main pipeline controller and contains the downstream 06-09 pipeline.

It:

1. checks whether stage 01 output exists
2. runs stage 01 only when required
3. checks whether stage 02 output exists
4. runs stage 02 only when required
5. loads extracted text
6. performs Stage 06 Qwen constraint extraction
7. performs Stage 07 deterministic normalization
8. performs Stage 08 validation
9. performs Stage 09 dataset export

Run this file for normal end-to-end execution.

---

## 3. Prerequisites

Stage 02 requires:

```bash
pip install requests pypdf pdfplumber pdf2image pytesseract
```

OCR also requires Tesseract and Poppler.

Ubuntu/Debian:

```bash
sudo apt install tesseract-ocr poppler-utils
```

The Qwen stage additionally requires configuration for the selected Qwen
deployment. The actual endpoint/model/key should be configured in `09_main.py`
once the deployment is finalized.

---

## 4. Input

The main metadata input is:

```text
gem_bids_metadata.csv
```

The pipeline is intended for the 2019+ GeM dataset.

Relevant metadata fields include:

```text
bid_id
bid_number
bid_year
buyer_org
department
product_category
category_family
quantity
bid_start_date
bid_end_date
bid_document_url
technical_spec_url
atc_url
boq_url
corrigendum_urls
eligibility_urls
catalogue_urls
other_document_urls
documents
```

Stage 01 uses this metadata to resolve the actual document set for each BID.

---

## 5. Normal End-to-End Run

The recommended command is:

```bash
python 09_main.py
```

For the current 10-BID test:

```python
MAX_BIDS = 10
RUN_UPSTREAM_IF_MISSING = True
FORCE_REDO = False
```

The controller behaves as:

```text
09_main.py
    |
    +-- 01 output missing?
    |      +-- YES -> run 01
    |
    +-- 02 output missing/incomplete?
    |      +-- YES -> run 02
    |
    +-- Stage 06 — Qwen
    +-- Stage 07 — Normalize
    +-- Stage 08 — Validate
    +-- Stage 09 — Export
```

---

## 6. Re-running the Pipeline

Running:

```bash
python 09_main.py
```

again does not automatically rerun stages 01 and 02.

If resolution and extraction are complete:

```text
01 -> SKIP
02 -> SKIP
06 -> RUN
07 -> RUN
08 -> RUN
09 -> RUN
```

This is the normal development workflow when changing the Qwen prompt,
normalization rules, validation rules, or export logic.

---

## 7. Missing Data Behavior

`09_main.py` checks generated files rather than assuming that a directory means
a stage succeeded.

For stage 01 it checks for:

```text
gem_pipeline_data/*/resolved_documents.json
```

For stage 02 it checks:

```text
pipeline_status.json
```

and verifies that referenced extracted text files actually exist.

For example:

```text
resolved_documents.json     OK
pipeline_status.json        OK
extracted/00_BID.txt        OK
extracted/01_ATC.txt        MISSING
```

results in:

```text
01 -> SKIP
02 -> RUN
06 -> RUN
07 -> RUN
08 -> RUN
09 -> RUN
```

---

## 8. `RUN_UPSTREAM_IF_MISSING`

In `09_main.py`:

```python
RUN_UPSTREAM_IF_MISSING = True
```

means:

> Automatically run stages 01 and/or 02 when required upstream data is missing
> or incomplete.

This is the recommended setting for normal execution.

If:

```python
RUN_UPSTREAM_IF_MISSING = False
```

the controller fails instead of automatically creating missing upstream data.

This is useful when you want downstream execution to depend strictly on already
prepared document data.

---

## 9. `FORCE_REDO`

The main rebuild switch is:

```python
FORCE_REDO = False
```

Normal mode:

```python
FORCE_REDO = False
```

reuses existing stage 01 and 02 outputs.

Force mode:

```python
FORCE_REDO = True
```

causes:

```text
01 -> FORCE RUN
02 -> FORCE RUN
06 -> RUN
07 -> RUN
08 -> RUN
09 -> RUN
```

The current force behavior is intended primarily for the small test dataset.
Before using force mode on hundreds or thousands of BIDs, review cleanup
behavior so existing data is not unnecessarily destroyed.

---

## 10. `MAX_BIDS`

For the current test:

```python
MAX_BIDS = 10
```

For the full 2019+ dataset:

```python
MAX_BIDS = None
```

Then:

```bash
python 09_main.py
```

uses the same pipeline logic for all available 2019+ BIDs.

---

## 11. Running Stage 01 Directly

Stage 01 can be run independently when document resolution needs to be rebuilt
or inspected.

```bash
python 01_resolve_documents.py
```

If the script supports the limit:

```bash
python 01_resolve_documents.py --max-bids 10
```

Output:

```text
gem_pipeline_data/
└── GEM_<YEAR>_B_<NUMBER>/
    └── resolved_documents.json
```

Do not run stage 01 repeatedly just to rerun Qwen. Once document resolution is
correct, let `09_main.py` reuse it.

---

## 12. Running Stage 02 Directly

Stage 02 consumes manifests created by stage 01.

```bash
python 02_download_extract.py
```

It does not call stage 01.

If no manifests exist, stage 02 reports that document resolution must be run
first.

For a limited test:

```bash
python 02_download_extract.py --max-bids 10
```

To force document re-extraction:

```bash
python 02_download_extract.py --max-bids 10 --force
```

This is useful when PDF extraction logic changes but document resolution does
not.

---

## 13. Why 02 Does Not Call 01

The dependency is intentionally:

```text
01
 |
 v
resolved_documents.json
 |
 v
02
 |
 v
extracted/*.txt
```

not:

```text
02
 |
 +-- calls 01
```

This keeps document resolution and document acquisition/extraction independent.

Benefits:

- document resolution is not repeated unnecessarily
- extraction can be rerun independently
- Qwen experiments do not trigger document discovery
- debugging is easier
- the pipeline can scale to the larger dataset

---

# 14. Stage 06 — Qwen Constraint Extraction

Stage 06 is implemented inside `09_main.py`.

Input:

```text
gem_pipeline_data/*/extracted/*.txt
```

Relevant source roles:

```text
BID
TECHNICAL_SPEC
BOQ
ATC
CORRIGENDUM
ELIGIBILITY
```

RA documents are retained for provenance but are not treated as an independent
constraint source because an RA can simply refer back to its parent BID.

Output:

```text
gem_pipeline_data/bid_constraints_raw.jsonl
```

The intended structure is:

```json
{
  "bid_id": "...",
  "bid_number": "...",
  "constraints": [
    {
      "source": "BID",
      "page": 2,
      "constraint_type": "product",
      "attribute": "delivery_days",
      "operator": "<=",
      "value": "15",
      "unit": "days",
      "hard_soft": "hard",
      "confidence": 0.96,
      "raw_text": "..."
    }
  ]
}
```

The extractor should only extract constraints explicitly supported by the
document text.

Constraint types include:

```text
product
certification
delivery
experience
licence
geography
price
quantity
supplier_eligibility
```

Supported operators:

```text
=
>=
<=
in
required
```

Every extracted constraint should retain evidence through `raw_text` and page
information where available.

---

# 15. Stage 07 — Normalization

Stage 07 is implemented inside `09_main.py`.

The normalization layer converts equivalent representations into canonical
forms.

Examples:

```text
iso9001
    ->
iso_9001

delivery period
    ->
delivery_days

minimum
    ->
>=

mandatory
    ->
required
```

Output:

```text
gem_pipeline_data/bid_constraints.jsonl
```

This stage is deterministic and does not require another LLM call.

---

# 16. Stage 08 — Validation

Stage 08 is implemented inside `09_main.py`.

Validation checks constraints for structural and evidence quality.

Examples:

```text
required field exists
operator is valid
confidence is in [0, 1]
raw_text exists
raw_text occurs in source text
```

Output:

```text
gem_pipeline_data/constraint_validation.jsonl
```

Invalid records are retained with validation errors rather than silently
discarded.

---

# 17. Stage 09 — Export

Stage 09 is implemented inside `09_main.py`.

The validated constraints are flattened into the research dataset format.

Output:

```text
gem_pipeline_data/bid_constraints.csv
```

Expected columns:

```text
bid_id
bid_number
constraint_id
source
constraint_type
attribute
operator
value
unit
hard_soft
confidence
raw_text
page
valid
validation_errors
```

This dataset can subsequently be joined with IndiaMART supplier information.

---

# 18. Downstream Switches

`09_main.py` contains switches for development:

```python
RUN_QWEN = True
RUN_NORMALIZATION = True
RUN_VALIDATION = True
RUN_EXPORT = True
```

For a normal downstream run:

```python
RUN_QWEN = True
RUN_NORMALIZATION = True
RUN_VALIDATION = True
RUN_EXPORT = True
```

while:

```python
FORCE_REDO = False
```

keeps stages 01 and 02 untouched when their outputs are already complete.

These switches allow individual downstream stages to be disabled while
developing or debugging.

---

# 19. Typical Development Workflows

## Initial 10-BID test

Configure:

```python
MAX_BIDS = 10
RUN_UPSTREAM_IF_MISSING = True
FORCE_REDO = False
```

Run:

```bash
python 09_main.py
```

Expected:

```text
01 -> run
02 -> run
06 -> run
07 -> run
08 -> run
09 -> run
```

## Re-run after changing the Qwen prompt

Keep:

```python
FORCE_REDO = False
```

Run:

```bash
python 09_main.py
```

Expected:

```text
01 -> skip
02 -> skip
06 -> run
07 -> run
08 -> run
09 -> run
```

This is the normal iteration loop for Qwen and downstream processing.

## Re-run extraction after changing PDF extraction logic

Run:

```bash
python 02_download_extract.py --max-bids 10 --force
```

or use the corresponding force behavior through `09_main.py`.

## Full rebuild

Set:

```python
FORCE_REDO = True
```

then:

```bash
python 09_main.py
```

After the rebuild, return:

```python
FORCE_REDO = False
```

---

# 20. Expected Directory Structure

After successful processing:

```text
gem_pipeline_data/
|
+-- GEM_2019_B_XXXXXX/
|   +-- resolved_documents.json
|   +-- pipeline_status.json
|   +-- downloaded/
|   +-- extracted/
|       +-- 00_BID.txt
|       +-- 01_TECHNICAL_SPEC.txt
|       +-- 02_ATC.txt
|       +-- ...
|
+-- GEM_2020_B_XXXXXX/
|   +-- resolved_documents.json
|   +-- pipeline_status.json
|   +-- extracted/
|       +-- ...
|
+-- bid_constraints_raw.jsonl
+-- bid_constraints.jsonl
+-- constraint_validation.jsonl
+-- bid_constraints.csv
```

The exact number and type of extracted documents varies by BID. Do not assume
that every GeM BID has the same number of PDFs.

---

# 21. Document Handling Rules

### BID

Primary source for procurement requirements.

### Technical specification

Primary source for product constraints.

### BOQ / price schedule

Used when it contains product, quantity, or commercial constraints.

### ATC

Used for buyer-specific commercial and supplier requirements.

### Corrigendum

Used when it modifies an existing requirement.

### Eligibility

Used for supplier eligibility requirements.

### RA

Retained for provenance, but normally excluded from independent constraint
extraction because it can refer back to the parent BID.

### Product catalogue

Not treated as a normal PDF extraction target when the URL is an HTML catalogue.

### Other

Stored and classified when possible, but not automatically assumed to contain
relevant constraints.

---

# 22. Failure Handling in Stage 02

Stage 02 uses this extraction order:

```text
download
   |
   v
pypdf
   |
   +-- sufficient text -> save
   |
   +-- insufficient
           |
           v
       pdfplumber
           |
           +-- sufficient text -> save
           |
           +-- insufficient
                   |
                   v
                  OCR
```

A PDF is deleted only after successful extraction and text persistence.

If extraction fails:

```text
PDF RETAINED FOR DEBUGGING
```

This is intentional.

---

# 23. Command Summary

### Normal full pipeline

```bash
python 09_main.py
```

### Run document resolution only

```bash
python 01_resolve_documents.py
```

### Run extraction only

```bash
python 02_download_extract.py
```

### Force extraction only

```bash
python 02_download_extract.py --force
```

### Test 10 BIDs

Set:

```python
MAX_BIDS = 10
```

then:

```bash
python 09_main.py
```

### Process all 2019+ BIDs

Set:

```python
MAX_BIDS = None
```

then:

```bash
python 09_main.py
```

### Force complete upstream rebuild

Set:

```python
FORCE_REDO = True
```

then:

```bash
python 09_main.py
```

Return it to:

```python
FORCE_REDO = False
```

after the rebuild.

---

# 24. Operational Rule

For normal use, run only:

```bash
python 09_main.py
```

Use `01_resolve_documents.py` and `02_download_extract.py` directly only when
debugging or specifically rebuilding an upstream stage.

The intended production flow is:

```text
                    +----------------------+
                    |      09_main.py      |
                    |    MAIN ENTRYPOINT   |
                    +----------+-----------+
                               |
                 +-------------+-------------+
                 |                           |
             UPSTREAM                    DOWNSTREAM
                 |                           |
          +------+-------+             +-----+------+
          |              |             |            |
          v              v             v            v
      01 resolve    02 extract      06 Qwen    07 normalize
                                      |            |
                                      +-----+------+
                                            |
                                            v
                                      08 validate
                                            |
                                            v
                                       09 export
```

This keeps document acquisition separate from downstream model experimentation
while giving `09_main.py` control over the complete end-to-end run.
