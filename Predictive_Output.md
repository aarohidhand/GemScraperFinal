

---

# GeM End-to-End Pipeline — Expected Outputs

```text
gem_bids_metadata.csv
        │
        ▼
┌──────────────────────────────┐
│ STAGE 01                     │
│ Document Resolution           │
└──────────────┬───────────────┘
               │
               ▼
       resolved_documents.json
               │
               ▼
┌──────────────────────────────┐
│ STAGE 02                     │
│ PDF Download + Text Extract  │
└──────────────┬───────────────┘
               │
               ▼
          extracted/*.txt
          pipeline_status.json
               │
               ▼
┌──────────────────────────────┐
│ STAGE 06                     │
│ Deterministic Extraction     │
└──────────────┬───────────────┘
               │
               ▼
     bid_constraints_raw.jsonl
               │
               ▼
┌──────────────────────────────┐
│ STAGE 07                     │
│ Normalization                │
└──────────────┬───────────────┘
               │
               ▼
       bid_constraints.jsonl
               │
               ▼
┌──────────────────────────────┐
│ STAGE 08                     │
│ Validation                   │
└──────────────┬───────────────┘
               │
               ▼
     constraint_validation.jsonl
               │
               ▼
┌──────────────────────────────┐
│ STAGE 09                     │
│ Dataset Export               │
└──────────────┬───────────────┘
               │
               ▼
          bid_constraints.csv

               │
               └──────────────► OPTIONAL
                                 QWEN AUDIT
                                 ↓
                         qwen_robustness_audit.jsonl
```

The important distinction is:

> **Each stage should have a clear input artifact and a clear output artifact.**

---

# Stage 01 — Document Resolution

### Purpose

Take the metadata CSV and determine **which documents belong to each BID**.

Your current resolver already does this. It classifies documents into roles such as:

```text
BID
RA
TECHNICAL_SPEC
ATC
BOQ
CORRIGENDUM
ELIGIBILITY
PRODUCT_CATALOGUE
OTHER
```

The resolver currently finds, for example:

```text
GEM/2019/B/175197

00 BID
    https://bidplus.gem.gov.in/showbidDocument/1193388

01 RA
    https://bidplus.gem.gov.in/showradocumentPdf/1299852
```

That is consistent with the actual run. 

### Disk output

```text
gem_pipeline_data/
└── GEM_2019_B_175197/
    └── resolved_documents.json
```

### Example `resolved_documents.json`

Conceptually:

```json
{
  "bid_number": "GEM/2019/B/175197",
  "bid_id": "...",
  "buyer_org": "...",
  "department": "Health And Family Welfare Department Delhi",
  "product_category": "Steel Clothes Lockers",

  "documents": [
    {
      "document_index": 0,
      "role": "BID",
      "source_url": "https://bidplus.gem.gov.in/showbidDocument/1193388"
    },
    {
      "document_index": 1,
      "role": "RA",
      "source_url": "https://bidplus.gem.gov.in/showradocumentPdf/1299852"
    }
  ]
}
```

### Stage 01 console

Something like:

```text
STAGE 01 — DOCUMENT RESOLUTION

Eligible 2019+ BIDs: 10283
Test mode: processing 10 BIDs

[1/10] GEM/2019/B/175197
    00 BID
    01 RA

[2/10] GEM/2019/B/175334
    00 BID
    01 RA

...

RESOLUTION COMPLETE

BIDs: 10
Documents: 20
```

Your actual resolver already produces essentially this output.  

---

# Stage 02 — Download + Text Extraction

### Purpose

Turn:

```text
PDF URL
```

into:

```text
raw extracted text
```

**Nothing structured yet.**

This distinction is important.

Stage 02 should NOT decide:

> "0.8 mm is a thickness constraint."

It should only preserve the source.

Your current Stage 02 uses:

```text
1. pypdf
2. pdfplumber
3. OCR
```

and chooses the first usable extraction method. 

### Disk output

For the first BID:

```text
gem_pipeline_data/
└── GEM_2019_B_175197/
    ├── resolved_documents.json
    ├── pipeline_status.json
    └── extracted/
        ├── 00_BID.txt
        └── 01_RA.txt
```

### `00_BID.txt`

This is exactly the kind of output you pasted:

```text
=== PAGE 1 ===

Bid Number: GEM/2019/B/175197
Dated: 18-02-2019

Bid Document
Bid Details

Bid End Date/Time 28-02-2019 13:00:00

...

Total Quantity 4

Item Category Steel Clothes Lockers

...

Technical Specifications

...

Number of compartments (Nos)
8 6, 8, 12, 18, 20, 24, 4, 10

...

=== PAGE 2 ===

...

Warrantee period in
number of years
1 1, 2, 3, 4, 5 Or higher

...

Consignees/Reporting Officer and Quantity

...
Quantity Delivery Days
4 15

...
```

The current Stage 02 deliberately preserves page boundaries when formatting extracted pages. 

### `pipeline_status.json`

This is metadata about the extraction:

```json
{
  "bid_number": "GEM/2019/B/175197",

  "documents": [
    {
      "role": "BID",
      "status": "COMPLETED",
      "extraction_method": "pypdf",
      "pages": 3,
      "characters": 3521,
      "text_path": ".../extracted/00_BID.txt"
    }
  ]
}
```

Your Stage 02 already records these fields. 

### Console output

For your sample:

```text
GEM/2019/B/175197

[00] BID
    Download attempt 1/3
    Downloaded 115.1 KB
    PDF deleted: 00_BID.pdf
    Extracted: 3,521 chars
    Method: pypdf
    Pages: 3
```

That is already what you're seeing. 

---

# Stage 06 — Deterministic Constraint Extraction

This is the **important stage**.

It converts raw text into structured constraints.

For your sample:

```text
Number of compartments (Nos)
8 6, 8, 12, 18, 20, 24, 4, 10
```

should become something along the lines of:

```json
{
  "bid_number": "GEM/2019/B/175197",

  "constraint_type": "technical_specification",

  "attribute": "number_of_compartments",

  "operator": "in",

  "value": [8, 6, 12, 18, 20, 24, 4, 10],

  "unit": "Nos",

  "hard_soft": "hard",

  "source_role": "BID",

  "page": 1,

  "raw_text": "Number of compartments (Nos)\n8 6, 8, 12, 18, 20, 24, 4, 10",

  "extraction_method": "deterministic"
}
```

Another:

```text
Sheet Thickness of door (mm)(+/- 5%)
0.8 *
```

becomes:

```json
{
  "attribute": "sheet_thickness_of_door",
  "operator": "approximately",
  "value": 0.8,
  "unit": "mm",
  "tolerance": 5,
  "hard_soft": "hard",
  "page": 1,
  "raw_text": "Sheet Thickness of door (mm)(+/- 5%)\n0.8 *"
}
```

And:

```text
Quantity Delivery Days
4 15
```

becomes:

```json
{
  "attribute": "delivery_days",
  "operator": "<=",
  "value": 15,
  "unit": "days",
  "hard_soft": "hard",
  "page": 2,
  "raw_text": "Quantity Delivery Days\n4 15"
}
```

The key thing is **evidence**.

Every constraint should be traceable back to:

```text
BID
→ page
→ exact source text
```

### Expected output

```text
bid_constraints_raw.jsonl
```

One JSON object per line.

For example:

```json
{"bid_number":"GEM/2019/B/175197","attribute":"total_quantity","operator":"=","value":4,"unit":"units","page":1,"raw_text":"Total Quantity 4","extraction_method":"deterministic"}
{"bid_number":"GEM/2019/B/175197","attribute":"number_of_compartments","operator":"in","value":[8,6,12,18,20,24,4,10],"unit":"Nos","page":1,"raw_text":"Number of compartments (Nos)\n8 6, 8, 12, 18, 20, 24, 4, 10","extraction_method":"deterministic"}
{"bid_number":"GEM/2019/B/175197","attribute":"sheet_thickness_body","operator":"approx","value":0.8,"unit":"mm","tolerance":5,"page":1,"extraction_method":"deterministic"}
{"bid_number":"GEM/2019/B/175197","attribute":"height","operator":"approx","value":1800,"unit":"mm","tolerance":5,"page":2,"extraction_method":"deterministic"}
{"bid_number":"GEM/2019/B/175197","attribute":"width","operator":"approx","value":910,"unit":"mm","tolerance":5,"page":2,"extraction_method":"deterministic"}
{"bid_number":"GEM/2019/B/175197","attribute":"depth","operator":"approx","value":480,"unit":"mm","tolerance":5,"page":2,"extraction_method":"deterministic"}
{"bid_number":"GEM/2019/B/175197","attribute":"warranty_period","operator":">=","value":1,"unit":"years","page":2,"extraction_method":"deterministic"}
{"bid_number":"GEM/2019/B/175197","attribute":"delivery_days","operator":"<=","value":15,"unit":"days","page":2,"extraction_method":"deterministic"}
```

### Console

This should eventually look more like:

```text
STAGE 06 — DETERMINISTIC CONSTRAINT EXTRACTION

SOURCE DOCUMENT CHECK
──────────────────────────────────────────────
GEM/2019/B/175197
    BID: 00_BID.txt
    3 pages
    3,521 chars
    ✓ usable

...

EXTRACTION
──────────────────────────────────────────────
[1/10] GEM/2019/B/175197: 18 constraints
[2/10] GEM/2019/B/175334: 24 constraints
[3/10] GEM/2019/B/175365: 16 constraints
...

Total constraints extracted: 213
```

That is much more useful than simply:

```text
[1/10] ...: 0 constraints
```

---

# Stage 07 — Normalization

Stage 06 says what the source **literally says**.

Stage 07 makes different representations consistent.

For example:

```text
"15 Days"
"15 days"
"15 day"
```

all become:

```json
{
  "value": 15,
  "unit": "days"
}
```

Similarly:

```text
Rs. 5,000
INR 5000
₹5000
```

could normalize to:

```json
{
  "value": 5000,
  "currency": "INR"
}
```

### Important distinction

Normalization should **not invent information**.

It can transform:

```text
0.8 mm (+/- 5%)
```

into:

```json
{
  "value": 0.8,
  "unit": "mm",
  "tolerance_percent": 5
}
```

But it should not decide:

```text
"commercial quality"
→ "Grade A"
```

unless there is an explicit deterministic mapping.

### Output

```text
bid_constraints.jsonl
```

Example:

```json
{
  "bid_number": "GEM/2019/B/175197",
  "attribute": "delivery_days",
  "operator": "<=",
  "value": 15,
  "unit": "days",
  "hard_soft": "hard",

  "source": {
    "role": "BID",
    "page": 2,
    "raw_text": "Quantity Delivery Days\n4 15"
  },

  "extraction_method": "deterministic",
  "normalized": true
}
```

### Console

```text
STAGE 07 — CONSTRAINT NORMALIZATION

[1/10] GEM/2019/B/175197
    Raw constraints: 18
    Normalized: 18
    Changed: 7

[2/10] GEM/2019/B/175334
    Raw constraints: 24
    Normalized: 24
    Changed: 11

...

Normalization complete.
Total normalized constraints: 213
```

---

# Stage 08 — Validation

This stage asks:

> **Does every structured constraint actually have valid evidence in the source?**

This is different from extraction.

For example:For one BID, the final output should be a **row-level constraint dataset**, with the original evidence preserved so every recommendation constraint can be traced back to the GeM document.

Using the `GEM/2019/B/175334` Almirah-Steel BID as the example, the pipeline has:

```text
01_resolve_documents.py
        ↓
resolved_documents.json
        ↓
02_download_extract.py
        ↓
00_BID.txt
01_RA.txt
        ↓
09_main.py
   ├── 06 Qwen
   ├── 07 Normalize
   ├── 08 Validate
   └── 09 Export
        ↓
bid_constraints.csv
```

The resolver identifies `GEM/2019/B/175334`, quantity 4, under the Health and Family Welfare Department Delhi, with the BID PDF and RA document resolved.  The extraction stage successfully produced a 5-page BID text file and a 1-page RA text file. 

## 1. `01_resolve_documents.py` output

For this BID:

```json
{
  "bid_id": "1193528",
  "bid_number": "GEM/2019/B/175334",
  "bid_year": "2019",
  "buyer_org": "",
  "department": "Health and Family Welfare Department Delhi",
  "product_category": "almirah- Steel",
  "category_family": "",
  "quantity": "4",

  "documents": [
    {
      "role": "BID",
      "source": "bid_document_url",
      "source_url": "https://bidplus.gem.gov.in/showbidDocument/1193528",
      "document_index": 0
    },
    {
      "role": "RA",
      "original_role": "OTHER",
      "source": "other_document_urls",
      "source_url": "https://bidplus.gem.gov.in/showradocumentPdf/1299850",
      "document_index": 1
    }
  ]
}
```

This is **document discovery/provenance**, not yet the recommendation dataset.

---

# 2. `02_download_extract.py` output

It creates:

```text


```json
{
  "attribute": "delivery_days",
  "value": 15,
  "operator": "<="
}
```

Validation checks:

```text
Does page 2 contain evidence?
Is the evidence associated with this BID?
Is the operator valid?
Is the value valid?
Is the unit valid?
Is confidence valid?
```

### Output

```text
constraint_validation.jsonl
```

Example:

```json
{
  "bid_number": "GEM/2019/B/175197",
  "constraint_id": "C-000123",

  "valid": true,

  "checks": {
    "required_fields": true,
    "operator_valid": true,
    "value_valid": true,
    "evidence_present": true,
    "evidence_in_source": true
  },

  "errors": []
}
```

If something is wrong:

```json
{
  "constraint_id": "C-000124",
  "valid": false,

  "errors": [
    "Evidence text not found in source document"
  ]
}
```

### Console

```text
STAGE 08 — CONSTRAINT VALIDATION

Constraints received: 213

Required fields       ✓ 213/213
Operators valid       ✓ 213/213
Values valid          ✓ 213/213
Evidence present      ✓ 213/213
Evidence in source    ✓ 210/213

VALID:   210
INVALID:   3
```

The invalid records should remain visible rather than disappearing.

---

# Stage 09 — Dataset Export

This is where the machine-readable dataset is produced.

### Output

```text
bid_constraints.csv
```

Something like:

| bid_number        | attribute       | operator |     value | unit  | hard_soft | page | source_role |
| ----------------- | --------------- | -------- | --------: | ----- | --------- | ---: | ----------- |
| GEM/2019/B/175197 | total_quantity  | =        |         4 | units | hard      |    1 | BID         |
| GEM/2019/B/175197 | compartments    | in       | 8,6,12... | Nos   | hard      |    1 | BID         |
| GEM/2019/B/175197 | sheet_thickness | approx   |       0.8 | mm    | hard      |    1 | BID         |
| GEM/2019/B/175197 | height          | approx   |      1800 | mm    | hard      |    2 | BID         |
| GEM/2019/B/175197 | width           | approx   |       910 | mm    | hard      |    2 | BID         |
| GEM/2019/B/175197 | delivery_days   | <=       |        15 | days  | hard      |    2 | BID         |
| GEM/2019/B/175197 | warranty        | >=       |         1 | years | hard      |    2 | BID         |

### Console

```text
STAGE 09 — DATASET EXPORT

Validated constraints: 210

Exported:
    bid_constraints.csv

Rows: 210
BIDs: 10
```

---

# Optional Qwen Audit

This is deliberately **not in the ground-truth path**.

The flow is:

```text
deterministic constraint
        +
original evidence
        ↓
      Qwen
        ↓
audit only
```

Qwen should produce something like:

```json
{
  "constraint_id": "C-000123",

  "supported": true,
  "hallucination": false,
  "evidence_match": true,

  "reason": "The source explicitly states Delivery Days = 15 on page 2."
}
```

Or:

```json
{
  "constraint_id": "C-000124",

  "supported": false,
  "hallucination": true,
  "evidence_match": false,

  "reason": "The extracted value 20 is not present in the cited source text."
}
```

### Output

```text
qwen_robustness_audit.jsonl
```

And critically:

```text
qwen_robustness_audit.jsonl
          X
          │
          │ does NOT modify
          ▼
bid_constraints.csv
```

It is an **audit dataset**, not the source of truth.

---

# What the final directory should look like

For one BID:

```text
gem_pipeline_data/
│
├── GEM_2019_B_175197/
│   │
│   ├── resolved_documents.json       ← Stage 01
│   ├── pipeline_status.json          ← Stage 02
│   │
│   └── extracted/
│       ├── 00_BID.txt                ← Stage 02
│       └── 01_RA.txt                 ← Stage 02
│
├── GEM_2019_B_175334/
│   ├── resolved_documents.json
│   ├── pipeline_status.json
│   └── extracted/
│       ├── 00_BID.txt
│       └── 01_RA.txt
│
├── ...
│
├── bid_constraints_raw.jsonl         ← Stage 06
├── bid_constraints.jsonl             ← Stage 07
├── constraint_validation.jsonl       ← Stage 08
├── bid_constraints.csv               ← Stage 09
└── qwen_robustness_audit.jsonl      ← Optional audit
```

## The critical invariant

The pipeline should satisfy this:

```text
Stage 01
    "Here are the documents."

Stage 02
    "Here is exactly what those documents say."

Stage 06
    "Here are the constraints explicitly extracted from that text."

Stage 07
    "Here are those same constraints in canonical form."

Stage 08
    "Here is whether each constraint is actually supported by the source."

Stage 09
    "Here is the validated dataset."

Qwen
    "Here is an independent audit of whether Stage 06 appears robust."
```

