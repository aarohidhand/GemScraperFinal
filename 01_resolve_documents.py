import csv
import json
import re
import shutil
from pathlib import Path
from urllib.parse import urlparse


# ============================================================
# CONFIG
# ============================================================

METADATA_CSV = Path("gem_bids_metadata.csv")

OUTPUT_ROOT = Path("gem_pipeline_data")

MIN_BID_YEAR = 2019

# ------------------------------------------------------------
# FIRST TEST:
#     10
#
# ALL BIDS:
#     None
# ------------------------------------------------------------

MAX_BIDS = 10


# ============================================================
# HELPERS
# ============================================================

def safe_name(value):
    value = str(value or "").strip()

    value = re.sub(
        r"[^A-Za-z0-9._-]+",
        "_",
        value,
    )

    return value.strip("_") or "unknown"


def normalize_url(url):

    if not url:
        return ""

    url = str(url).strip()

    if url.startswith("//"):
        return "https:" + url

    if url.startswith("/"):
        return "https://bidplus.gem.gov.in" + url

    return url


def allowed_bid(bid_number):

    match = re.match(
        r"^GEM/(\d{4})/B/",
        str(bid_number or "").strip(),
    )

    if not match:
        return False

    return int(match.group(1)) >= MIN_BID_YEAR


def parse_json_list(value):

    if not value:
        return []

    try:
        value = json.loads(value)

        if isinstance(value, list):
            return value

    except Exception:
        pass

    return []


# ============================================================
# DOCUMENT ROLE CLASSIFICATION
# ============================================================

def classify_role(
    role,
    url,
    document_type="",
):
    """
    Classify a document conservatively.

    Explicit role wins.

    URL/document-type clues are then used.

    Unknown documents remain OTHER rather than being
    incorrectly classified.
    """

    role = str(role or "").upper().strip()
    document_type = str(
        document_type or ""
    ).upper().strip()

    url_lower = str(
        url or ""
    ).lower()

    combined = (
        role
        + " "
        + document_type
        + " "
        + url_lower
    )

    # --------------------------------------------------------
    # Explicit roles
    # --------------------------------------------------------

    if role in {
        "BID",
        "TECHNICAL_SPEC",
        "ATC",
        "BOQ",
        "CORRIGENDUM",
        "ELIGIBILITY",
        "PRODUCT_CATALOGUE",
        "RA",
    }:
        return role

    # --------------------------------------------------------
    # URL patterns
    # --------------------------------------------------------

    if "showcatalogue" in url_lower:
        return "PRODUCT_CATALOGUE"

    if "showradocumentpdf" in url_lower:
        return "RA"

    if "showdirectradocumentpdf" in url_lower:
        return "RA"

    if "showbiddocument" in url_lower:
        return "BID"

    # --------------------------------------------------------
    # Text clues
    # --------------------------------------------------------

    if any(
        x in combined
        for x in [
            "technical specification",
            "technical_specification",
            "technical spec",
            "technical_spec",
            "technicalspecification",
        ]
    ):
        return "TECHNICAL_SPEC"

    if any(
        x in combined
        for x in [
            "additional terms",
            "additional_terms",
            "additional terms and conditions",
            "atc",
        ]
    ):
        return "ATC"

    if any(
        x in combined
        for x in [
            "boq",
            "bill of quantity",
            "bill_of_quantity",
            "price schedule",
            "price_schedule",
        ]
    ):
        return "BOQ"

    if any(
        x in combined
        for x in [
            "corrigendum",
            "corrigenda",
        ]
    ):
        return "CORRIGENDUM"

    if any(
        x in combined
        for x in [
            "eligibility",
            "qualification",
        ]
    ):
        return "ELIGIBILITY"

    return "OTHER"


# ============================================================
# LOAD CSV
# ============================================================

def load_csv():

    if not METADATA_CSV.exists():

        raise FileNotFoundError(
            f"Metadata CSV not found:\n"
            f"{METADATA_CSV.resolve()}"
        )

    with METADATA_CSV.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        reader = csv.DictReader(f)

        rows = list(reader)

    return rows


# ============================================================
# RESOLVE ONE BID
# ============================================================

def resolve_bid(row):

    bid_number = (
        row.get("bid_number") or ""
    ).strip()

    bid_id = (
        row.get("bid_id") or ""
    ).strip()

    documents = []

    # --------------------------------------------------------
    # Add document helper
    # --------------------------------------------------------

    def add_document(
        url,
        role=None,
        document_id=None,
        document_type=None,
        source=None,
    ):

        url = normalize_url(url)

        if not url:
            return

        resolved_role = classify_role(
            role,
            url,
            document_type,
        )

        documents.append({
            "document_id": document_id,
            "role": resolved_role,
            "original_role": role or "",
            "document_type": document_type or "",
            "source": source or "csv",
            "source_url": url,
        })

    # --------------------------------------------------------
    # Explicit canonical URL columns
    # --------------------------------------------------------

    add_document(
        row.get("bid_document_url"),
        role="BID",
        source="bid_document_url",
    )

    add_document(
        row.get("technical_spec_url"),
        role="TECHNICAL_SPEC",
        source="technical_spec_url",
    )

    add_document(
        row.get("atc_url"),
        role="ATC",
        source="atc_url",
    )

    add_document(
        row.get("boq_url"),
        role="BOQ",
        source="boq_url",
    )

    # --------------------------------------------------------
    # Multiple URL columns
    # --------------------------------------------------------

    for url in parse_json_list(
        row.get("corrigendum_urls")
    ):

        add_document(
            url,
            role="CORRIGENDUM",
            source="corrigendum_urls",
        )

    for url in parse_json_list(
        row.get("eligibility_urls")
    ):

        add_document(
            url,
            role="ELIGIBILITY",
            source="eligibility_urls",
        )

    for url in parse_json_list(
        row.get("catalogue_urls")
    ):

        add_document(
            url,
            role="PRODUCT_CATALOGUE",
            source="catalogue_urls",
        )

    for url in parse_json_list(
        row.get("other_document_urls")
    ):

        add_document(
            url,
            role="OTHER",
            source="other_document_urls",
        )

    # --------------------------------------------------------
    # Complete document inventory
    # --------------------------------------------------------

    for item in parse_json_list(
        row.get("documents")
    ):

        if not isinstance(item, dict):
            continue

        add_document(
            item.get("source_url"),
            role=item.get("role"),
            document_id=item.get(
                "document_id"
            ),
            document_type=item.get(
                "document_type"
            ),
            source="documents",
        )

    # --------------------------------------------------------
    # Deduplicate by URL
    # --------------------------------------------------------

    by_url = {}

    priority = {
        "BID": 100,
        "TECHNICAL_SPEC": 90,
        "ATC": 80,
        "BOQ": 70,
        "CORRIGENDUM": 60,
        "ELIGIBILITY": 50,
        "PRODUCT_CATALOGUE": 40,
        "RA": 30,
        "OTHER": 10,
    }

    for doc in documents:

        url = doc["source_url"]

        if url not in by_url:

            by_url[url] = doc

        else:

            existing = by_url[url]

            if (
                priority.get(
                    doc["role"],
                    0,
                )
                >
                priority.get(
                    existing["role"],
                    0,
                )
            ):
                by_url[url] = doc

    documents = list(
        by_url.values()
    )

    # --------------------------------------------------------
    # Stable ordering
    # --------------------------------------------------------

    role_order = {
        "BID": 0,
        "TECHNICAL_SPEC": 1,
        "ATC": 2,
        "BOQ": 3,
        "CORRIGENDUM": 4,
        "ELIGIBILITY": 5,
        "PRODUCT_CATALOGUE": 6,
        "RA": 7,
        "OTHER": 8,
    }

    documents.sort(
        key=lambda x: (
            role_order.get(
                x["role"],
                99,
            ),
            x["source_url"],
        )
    )

    # --------------------------------------------------------
    # Assign processing index
    # --------------------------------------------------------

    for index, doc in enumerate(
        documents
    ):

        doc["document_index"] = index

    return {
        "bid_id": bid_id,
        "bid_number": bid_number,
        "bid_year": row.get(
            "bid_year",
            "",
        ),
        "buyer_org": row.get(
            "buyer_org",
            "",
        ),
        "department": row.get(
            "department",
            "",
        ),
        "product_category": row.get(
            "product_category",
            "",
        ),
        "category_family": row.get(
            "category_family",
            "",
        ),
        "quantity": row.get(
            "quantity",
            "",
        ),
        "bid_start_date": row.get(
            "bid_start_date",
            "",
        ),
        "bid_end_date": row.get(
            "bid_end_date",
            "",
        ),
        "documents": documents,
    }


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 90)
    print("01 — GeM DOCUMENT RESOLVER")
    print("=" * 90)

    rows = load_csv()

    # --------------------------------------------------------
    # Filter 2019+
    # --------------------------------------------------------

    rows = [
        row
        for row in rows
        if allowed_bid(
            row.get("bid_number")
        )
    ]

    print(
        f"Eligible 2019+ BIDs: "
        f"{len(rows)}"
    )

    # --------------------------------------------------------
    # Limit
    # --------------------------------------------------------

    if MAX_BIDS is not None:

        rows = rows[:MAX_BIDS]

        print(
            f"Test mode: processing "
            f"{len(rows)} BIDs"
        )

    else:

        print(
            "ALL mode: processing every "
            "2019+ BID"
        )

    # --------------------------------------------------------
    # Completely rebuild generated data
    # --------------------------------------------------------

    if OUTPUT_ROOT.exists():

        print(
            f"\nRemoving previous generated data:\n"
            f"{OUTPUT_ROOT.resolve()}"
        )

        shutil.rmtree(
            OUTPUT_ROOT
        )

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Process
    # --------------------------------------------------------

    total_documents = 0

    for index, row in enumerate(
        rows,
        start=1,
    ):

        bid_number = (
            row.get("bid_number") or ""
        ).strip()

        print(
            f"\n[{index}/{len(rows)}] "
            f"{bid_number}"
        )

        resolved = resolve_bid(row)

        bid_dir = (
            OUTPUT_ROOT
            / safe_name(bid_number)
        )

        bid_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        manifest_path = (
            bid_dir
            / "resolved_documents.json"
        )

        manifest_path.write_text(
            json.dumps(
                resolved,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        documents = resolved[
            "documents"
        ]

        total_documents += len(
            documents
        )

        for doc in documents:

            print(
                f"    "
                f"{doc['document_index']:02d} "
                f"{doc['role']:20s} "
                f"{doc['source_url']}"
            )

    print("\n")
    print("=" * 90)
    print("RESOLUTION COMPLETE")
    print("=" * 90)

    print(
        f"BIDs: {len(rows)}"
    )

    print(
        f"Documents: {total_documents}"
    )

    print(
        f"Output:\n"
        f"{OUTPUT_ROOT.resolve()}"
    )


if __name__ == "__main__":
    main()