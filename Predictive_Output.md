For one BID, the final output should be a **row-level constraint dataset**, with the original evidence preserved so every recommendation constraint can be traced back to the GeM document.

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
gem_pipeline_data/
└── GEM_2019_B_175334/
    ├── resolved_documents.json
    ├── pipeline_status.json
    │
    ├── downloaded/
    │
    └── extracted/
        ├── 00_BID.txt
        └── 01_RA.txt
```

The status looks approximately like:

```json
{
  "bid_id": "1193528",
  "bid_number": "GEM/2019/B/175334",

  "documents": [
    {
      "role": "BID",
      "status": "COMPLETED",
      "extraction_method": "pypdf",
      "pages": 5,
      "characters": 5608,
      "text_path":
        "gem_pipeline_data/GEM_2019_B_175334/extracted/00_BID.txt"
    },
    {
      "role": "RA",
      "status": "COMPLETED",
      "extraction_method": "pypdf",
      "pages": 1,
      "characters": 846,
      "text_path":
        "gem_pipeline_data/GEM_2019_B_175334/extracted/01_RA.txt"
    }
  ]
}
```

That is exactly the kind of successful extraction shown by the uploaded status. 

---

# 3. What Qwen should produce

This is the important part.

Suppose the BID text contains requirements such as the specifications for the steel almirah. Qwen should turn them into **atomic constraints**, rather than producing one giant description.

For example, conceptually:

```json
{
  "bid_id": "1193528",
  "bid_number": "GEM/2019/B/175334",

  "constraints": [
    {
      "source": "BID",
      "page": 2,
      "constraint_type": "product",
      "attribute": "material",
      "operator": "=",
      "value": "steel",
      "unit": "",
      "hard_soft": "hard",
      "confidence": 0.99,
      "raw_text": "..."
    },

    {
      "source": "BID",
      "page": 2,
      "constraint_type": "product",
      "attribute": "dimensions",
      "operator": "=",
      "value": "...",
      "unit": "",
      "hard_soft": "hard",
      "confidence": 0.98,
      "raw_text": "..."
    },

    {
      "source": "BID",
      "page": 2,
      "constraint_type": "product",
      "attribute": "door_type",
      "operator": "=",
      "value": "...",
      "unit": "",
      "hard_soft": "hard",
      "confidence": 0.96,
      "raw_text": "..."
    },

    {
      "source": "BID",
      "page": 3,
      "constraint_type": "delivery",
      "attribute": "delivery_days",
      "operator": "<=",
      "value": "...",
      "unit": "days",
      "hard_soft": "hard",
      "confidence": 0.99,
      "raw_text": "..."
    }
  ]
}
```

**Those values should only be populated from the actual extracted text.** I would not invent the exact specification values here when the purpose is to show your actual final dataset.

The key is the shape:

```text
one BID
   ↓
many atomic constraints
```

not:

```text
one BID
   ↓
one giant LLM description
```

---

# 4. After Stage 07 normalization

Qwen's output gets normalized deterministically.

For example:

```text
"minimum"
       ↓
">="

"mandatory"
       ↓
"required"

"delivery period"
       ↓
"delivery_days"

"ISO 9001"
       ↓
"iso_9001"
```

So the canonical representation becomes:

```json
{
  "bid_id": "1193528",
  "bid_number": "GEM/2019/B/175334",

  "constraints": [
    {
      "source": "BID",
      "constraint_type": "product",
      "attribute": "material",
      "operator": "=",
      "value": "steel",
      "unit": "",
      "hard_soft": "hard",
      "confidence": 0.99,
      "raw_text": "...",
      "page": 2
    }
  ]
}
```

---

# 5. After Stage 08 validation

Now each constraint gets validation information:

```json
{
  "source": "BID",
  "constraint_type": "delivery",
  "attribute": "delivery_days",
  "operator": "<=",
  "value": "...",
  "unit": "days",
  "hard_soft": "hard",
  "confidence": 0.99,
  "raw_text": "...",
  "page": 3,

  "validation": {
    "valid": true,
    "errors": []
  }
}
```

If Qwen hallucinated something, for example:

```json
{
  "attribute": "fire_rating",
  "value": "2 hours",
  "raw_text": "Fire rating: 2 hours",

  "validation": {
    "valid": false,
    "errors": [
      "evidence_not_found"
    ]
  }
}
```

That constraint isn't silently trusted.

---

# 6. Final `bid_constraints.csv`

This is the most important final artifact.

For `GEM/2019/B/175334`, it would look like:

| bid_id  | bid_number        | constraint_id | source | constraint_type | attribute     | operator | value | unit | hard_soft | confidence | raw_text          | page | valid |
| ------- | ----------------- | ------------- | ------ | --------------- | ------------- | -------- | ----- | ---- | --------- | ---------: | ----------------- | ---: | ----- |
| 1193528 | GEM/2019/B/175334 | 1193528_1     | BID    | product         | material      | =        | steel |      | hard      |       0.99 | evidence from BID |    2 | true  |
| 1193528 | GEM/2019/B/175334 | 1193528_2     | BID    | product         | dimensions    | =        | …     |      | hard      |       0.98 | evidence from BID |    2 | true  |
| 1193528 | GEM/2019/B/175334 | 1193528_3     | BID    | product         | …             | =        | …     |      | hard      |       0.97 | evidence from BID |    2 | true  |
| 1193528 | GEM/2019/B/175334 | 1193528_4     | BID    | delivery        | delivery_days | <=       | …     | days | hard      |       0.99 | evidence from BID |    3 | true  |

The exact values in the real CSV come from `00_BID.txt`; the table above is showing the **format**, not inventing the missing specification values.

---

# 7. Why this structure matters for the recommender

This is where the dataset becomes useful for your actual SCM recommender.

Later, you have:

```text
GeM BID
   │
   ├── product constraints
   ├── certification constraints
   ├── delivery constraints
   ├── supplier eligibility
   ├── geography
   ├── quantity
   └── commercial constraints
             │
             ▼
      Constraint Validator
             │
             ▼
       IndiaMART suppliers
```

For example, a supplier might have:

```json
{
  "supplier_id": "IM_12345",
  "product": "Steel Almirah",
  "material": "CR steel",
  "dimensions": "...",
  "delivery_days": 10,
  "location": "Delhi",
  "certifications": ["ISO 9001"]
}
```

The recommender can then evaluate:

```text
BID constraint                  Supplier
------------------------------------------------
material = steel          →     steel       ✓
delivery_days <= 15       →     10          ✓
ISO 9001 required         →     ISO 9001    ✓
geography = Delhi         →     Delhi       ✓
```

That gives you an actual **constraint-grounded supplier recommendation**, rather than semantic similarity alone.

And crucially, because every constraint retains:

```text
source
page
raw_text
confidence
validation
```

you can later explain:

> Supplier X satisfies the required delivery constraint because its stated delivery period is within the BID requirement.

That provenance is what makes the dataset much more defensible for the research paper.
