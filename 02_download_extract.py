import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests
import pdfplumber
import pytesseract

from pypdf import PdfReader
from pdf2image import convert_from_path


# ============================================================
# CONFIG
# ============================================================

METADATA_CSV = Path(
    "gem_bids_metadata.csv"
)

OUTPUT_ROOT = Path(
    "gem_pipeline_data"
)

REQUEST_TIMEOUT = 60
DOWNLOAD_RETRIES = 3

MIN_NATIVE_TEXT_CHARS = 100

OCR_DPI = 200

USER_AGENT = (
    "Mozilla/5.0 "
    "(Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/139.0 Safari/537.36"
)


# ============================================================
# SESSION
# ============================================================

session = requests.Session()

session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept": "*/*",
})


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


def is_pdf(content, content_type):

    content_type = (
        content_type or ""
    ).lower()

    if content.startswith(b"%PDF"):
        return True

    if "application/pdf" in content_type:
        return content.lstrip().startswith(
            b"%PDF"
        )

    return False


# ============================================================
# DOCUMENT ROLE FROM TEXT
# ============================================================

def refine_role_from_text(
    current_role,
    text,
):
    """
    Only refine OTHER.

    Explicit roles such as BID, RA, ATC,
    TECHNICAL_SPEC, BOQ etc. are never overwritten.
    """

    if current_role != "OTHER":
        return current_role

    sample = text[:12000].lower()

    if (
        "ra number:" in sample
        or "ra document" in sample
    ):
        return "RA"

    if (
        "bid number:" in sample
        or "bid document" in sample
    ):
        return "BID"

    if (
        "additional terms and conditions"
        in sample
        or "buyer specific additional"
        in sample
    ):
        return "ATC"

    if (
        "technical specifications"
        in sample
        or "specification specification name"
        in sample
    ):
        return "TECHNICAL_SPEC"

    if (
        "bill of quantity"
        in sample
        or "price schedule"
        in sample
        or "boq"
        in sample
    ):
        return "BOQ"

    if "corrigendum" in sample:
        return "CORRIGENDUM"

    if (
        "eligibility criteria"
        in sample
        or "qualification criteria"
        in sample
    ):
        return "ELIGIBILITY"

    return "OTHER"


# ============================================================
# DOWNLOAD
# ============================================================

def download_pdf(url, pdf_path):

    last_error = None

    for attempt in range(
        1,
        DOWNLOAD_RETRIES + 1,
    ):

        try:

            print(
                f"      Download attempt "
                f"{attempt}/{DOWNLOAD_RETRIES}"
            )

            response = session.get(
                url,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
            )

            if response.status_code != 200:
                raise RuntimeError(
                    f"HTTP {response.status_code}"
                )

            content = response.content

            content_type = response.headers.get(
                "Content-Type",
                "",
            )

            if not is_pdf(
                content,
                content_type,
            ):

                preview = (
                    content[:300]
                    .decode(
                        "utf-8",
                        errors="replace",
                    )
                )

                raise RuntimeError(
                    "URL did not return PDF. "
                    f"Content-Type={content_type!r}; "
                    f"preview={preview!r}"
                )

            pdf_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            pdf_path.write_bytes(content)

            print(
                f"      Downloaded "
                f"{len(content) / 1024:.1f} KB"
            )

            return True, None

        except Exception as e:

            last_error = str(e)

            print(
                f"      Download failed: {e}"
            )

            if attempt < DOWNLOAD_RETRIES:
                time.sleep(2 * attempt)

    return False, last_error


# ============================================================
# PYPDF
# ============================================================

def extract_pypdf(pdf_path):

    reader = PdfReader(
        str(pdf_path)
    )

    pages = []

    for page_number, page in enumerate(
        reader.pages,
        start=1,
    ):

        try:
            text = (
                page.extract_text()
                or ""
            )
        except Exception:
            text = ""

        pages.append({
            "page": page_number,
            "text": text,
        })

    chars = sum(
        len(p["text"])
        for p in pages
    )

    return pages, chars


# ============================================================
# PDFPLUMBER
# ============================================================

def extract_pdfplumber(pdf_path):

    pages = []

    with pdfplumber.open(
        str(pdf_path)
    ) as pdf:

        for page_number, page in enumerate(
            pdf.pages,
            start=1,
        ):

            try:

                text = (
                    page.extract_text(
                        x_tolerance=2,
                        y_tolerance=3,
                    )
                    or ""
                )

            except Exception:

                text = ""

            pages.append({
                "page": page_number,
                "text": text,
            })

    chars = sum(
        len(p["text"])
        for p in pages
    )

    return pages, chars


# ============================================================
# OCR
# ============================================================

def extract_ocr(pdf_path):

    print(
        "      Native extraction insufficient; "
        "running OCR"
    )

    images = convert_from_path(
        str(pdf_path),
        dpi=OCR_DPI,
    )

    pages = []

    for page_number, image in enumerate(
        images,
        start=1,
    ):

        print(
            f"        OCR "
            f"{page_number}/{len(images)}"
        )

        text = pytesseract.image_to_string(
            image,
            config="--psm 6",
        )

        pages.append({
            "page": page_number,
            "text": text or "",
        })

    chars = sum(
        len(p["text"])
        for p in pages
    )

    return pages, chars


# ============================================================
# FORMAT
# ============================================================

def format_pages(pages):

    output = []

    for page in pages:

        output.append(
            f"=== PAGE {page['page']} ==="
        )

        output.append("")

        output.append(
            page["text"].strip()
        )

        output.append("")

    return "\n".join(output)


# ============================================================
# EXTRACT TEXT
# ============================================================

def extract_text(pdf_path):

    # --------------------------------------------------------
    # 1. pypdf
    # --------------------------------------------------------

    try:

        pages, chars = extract_pypdf(
            pdf_path
        )

        if chars >= MIN_NATIVE_TEXT_CHARS:

            return (
                format_pages(pages),
                "pypdf",
                len(pages),
            )

    except Exception as e:

        print(
            f"      pypdf failed: {e}"
        )

    # --------------------------------------------------------
    # 2. pdfplumber
    # --------------------------------------------------------

    try:

        pages, chars = extract_pdfplumber(
            pdf_path
        )

        if chars >= MIN_NATIVE_TEXT_CHARS:

            return (
                format_pages(pages),
                "pdfplumber",
                len(pages),
            )

    except Exception as e:

        print(
            f"      pdfplumber failed: {e}"
        )

    # --------------------------------------------------------
    # 3. OCR
    # --------------------------------------------------------

    pages, chars = extract_ocr(
        pdf_path
    )

    if chars < 1:

        raise RuntimeError(
            "OCR produced no text"
        )

    return (
        format_pages(pages),
        "ocr",
        len(pages),
    )


# ============================================================
# MANIFEST VALIDATION
# ============================================================

def manifest_has_usable_extraction(
    manifest_path
):
    """
    Used by 09_main.py to decide whether 02
    needs to run.

    A BID is considered complete only when:
      - resolved_documents.json exists
      - every non-catalogue document has
        a successfully extracted text file
    """

    if not manifest_path.exists():
        return False

    try:

        manifest = json.loads(
            manifest_path.read_text(
                encoding="utf-8"
            )
        )

    except Exception:

        return False

    bid_dir = manifest_path.parent

    status_path = (
        bid_dir / "pipeline_status.json"
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
        []
    )

    if not documents:
        return False

    for doc in documents:

        status_value = doc.get(
            "status",
            ""
        )

        # Product catalogue is intentionally
        # not downloaded/extracted.
        if status_value == (
            "SKIPPED_PRODUCT_CATALOGUE"
        ):
            continue

        if "FAILED" in status_value:
            return False

        text_path = doc.get(
            "text_path"
        )

        if not text_path:
            return False

        if not Path(text_path).exists():
            return False

    return True


# ============================================================
# PROCESS ONE BID
# ============================================================

def process_bid(manifest_path):

    manifest = json.loads(
        manifest_path.read_text(
            encoding="utf-8"
        )
    )

    bid_number = manifest[
        "bid_number"
    ]

    bid_dir = manifest_path.parent

    downloaded_dir = (
        bid_dir / "downloaded"
    )

    extracted_dir = (
        bid_dir / "extracted"
    )

    downloaded_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    extracted_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("\n")
    print("=" * 90)
    print(bid_number)
    print("=" * 90)

    results = []

    for doc in manifest["documents"]:

        index = doc[
            "document_index"
        ]

        role = doc[
            "role"
        ]

        url = doc[
            "source_url"
        ]

        print(
            f"\n  [{index:02d}] {role}"
        )

        print(
            f"      {url}"
        )

        # ----------------------------------------------------
        # PRODUCT CATALOGUE
        # ----------------------------------------------------

        if role == "PRODUCT_CATALOGUE":

            print(
                "      SKIPPED: "
                "PRODUCT_CATALOGUE is not PDF"
            )

            results.append({
                **doc,
                "status":
                    "SKIPPED_PRODUCT_CATALOGUE",
            })

            continue

        # ----------------------------------------------------
        # Existing successful extraction
        #
        # This is important:
        # running 02 normally does not redownload
        # documents that are already successfully extracted.
        # ----------------------------------------------------

        existing_status = (
            bid_dir
            / "pipeline_status.json"
        )

        if existing_status.exists():

            try:

                old_status = json.loads(
                    existing_status.read_text(
                        encoding="utf-8"
                    )
                )

                old_docs = {
                    d.get("source_url"): d
                    for d in old_status.get(
                        "documents",
                        []
                    )
                }

                old_doc = old_docs.get(
                    url
                )

                if old_doc:

                    old_text_path = old_doc.get(
                        "text_path"
                    )

                    old_status_value = old_doc.get(
                        "status",
                        ""
                    )

                    if (
                        old_text_path
                        and Path(
                            old_text_path
                        ).exists()
                        and "FAILED"
                        not in old_status_value
                    ):

                        print(
                            "      EXISTS: "
                            "using existing extraction"
                        )

                        results.append(
                            old_doc
                        )

                        continue

            except Exception:
                pass

        # ----------------------------------------------------
        # Filenames
        # ----------------------------------------------------

        pdf_name = (
            f"{index:02d}_{role}.pdf"
        )

        txt_name = (
            f"{index:02d}_{role}.txt"
        )

        pdf_path = (
            downloaded_dir
            / pdf_name
        )

        txt_path = (
            extracted_dir
            / txt_name
        )

        # ----------------------------------------------------
        # Download
        # ----------------------------------------------------

        ok, error = download_pdf(
            url,
            pdf_path,
        )

        if not ok:

            print(
                "      DOWNLOAD FAILED"
            )

            results.append({
                **doc,
                "status":
                    "DOWNLOAD_FAILED",
                "error": error,
            })

            continue

        # ----------------------------------------------------
        # Extract
        # ----------------------------------------------------

        try:

            text, method, pages = (
                extract_text(
                    pdf_path
                )
            )

        except Exception as e:

            print(
                f"      EXTRACTION FAILED: {e}"
            )

            print(
                "      PDF RETAINED "
                "FOR DEBUGGING"
            )

            results.append({
                **doc,
                "status":
                    "EXTRACTION_FAILED",
                "error": str(e),
                "pdf_path": str(
                    pdf_path
                ),
            })

            continue

        # ----------------------------------------------------
        # Refine ONLY OTHER
        # ----------------------------------------------------

        final_role = (
            refine_role_from_text(
                role,
                text,
            )
        )

        if final_role != role:

            new_txt_name = (
                f"{index:02d}_"
                f"{final_role}.txt"
            )

            new_txt_path = (
                extracted_dir
                / new_txt_name
            )

        else:

            new_txt_path = txt_path

        # ----------------------------------------------------
        # Save text
        # ----------------------------------------------------

        new_txt_path.write_text(
            text,
            encoding="utf-8",
        )

        # ----------------------------------------------------
        # Delete PDF only after extraction
        # ----------------------------------------------------

        try:

            pdf_path.unlink()

            pdf_deleted = True

            print(
                f"      PDF deleted: "
                f"{pdf_path.name}"
            )

        except Exception as e:

            pdf_deleted = False

            print(
                f"      WARNING: PDF could "
                f"not be deleted: {e}"
            )

        print(
            f"      Extracted: "
            f"{len(text):,} chars"
        )

        print(
            f"      Method: {method}"
        )

        print(
            f"      Pages: {pages}"
        )

        if final_role != role:

            print(
                f"      Role refined: "
                f"{role} -> {final_role}"
            )

        results.append({
            **doc,
            "original_role": role,
            "role": final_role,
            "status": (
                "COMPLETED"
                if pdf_deleted
                else
                "EXTRACTED_PDF_DELETE_FAILED"
            ),
            "extraction_method": method,
            "pages": pages,
            "characters": len(text),
            "text_path": str(
                new_txt_path
            ),
        })

    # --------------------------------------------------------
    # Save status
    # --------------------------------------------------------

    status = {
        "bid_id": manifest[
            "bid_id"
        ],
        "bid_number": bid_number,
        "documents": results,
    }

    status_path = (
        bid_dir
        / "pipeline_status.json"
    )

    status_path.write_text(
        json.dumps(
            status,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return results


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Stage 02: Download and extract "
            "GeM documents"
        )
    )

    parser.add_argument(
        "--max-bids",
        type=int,
        default=None,
        help=(
            "Maximum number of BIDs to process. "
            "Default: all resolved BIDs."
        ),
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Force re-download and re-extraction "
            "of existing documents."
        ),
    )

    args = parser.parse_args()

    print("=" * 90)
    print("02 — GeM DOWNLOAD + TEXT EXTRACTION")
    print("=" * 90)

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # 02 NEVER calls 01 automatically.
    #
    # 09_main.py is responsible for deciding whether
    # document resolution is required.
    # --------------------------------------------------------

    manifests = sorted(
        OUTPUT_ROOT.glob(
            "*/resolved_documents.json"
        )
    )

    if args.max_bids is not None:

        manifests = manifests[
            :args.max_bids
        ]

    print(
        f"\nResolved BIDs found: "
        f"{len(manifests)}"
    )

    if not manifests:

        raise RuntimeError(
            "No resolved_documents.json files found. "
            "Run 01_resolve_documents.py first."
        )

    total_completed = 0
    total_failed = 0
    total_skipped = 0
    total_existing = 0

    for index, manifest_path in enumerate(
        manifests,
        start=1,
    ):

        print(
            f"\n\nBID "
            f"{index}/{len(manifests)}"
        )

        if (
            not args.force
            and manifest_has_usable_extraction(
                manifest_path
            )
        ):

            print(
                "  SKIPPING BID: "
                "existing extraction is complete"
            )

            total_existing += 1

            continue

        try:

            # ------------------------------------------------
            # If --force is enabled, remove generated
            # extraction/download artifacts for this BID.
            # ------------------------------------------------

            if args.force:

                bid_dir = manifest_path.parent

                for dirname in (
                    "downloaded",
                    "extracted",
                ):

                    directory = (
                        bid_dir / dirname
                    )

                    if directory.exists():

                        for child in directory.iterdir():

                            if child.is_file():
                                child.unlink()

                status_path = (
                    bid_dir
                    / "pipeline_status.json"
                )

                if status_path.exists():
                    status_path.unlink()

            results = process_bid(
                manifest_path
            )

            total_completed += sum(
                r["status"]
                == "COMPLETED"
                for r in results
            )

            total_failed += sum(
                "FAILED"
                in r["status"]
                for r in results
            )

            total_skipped += sum(
                r["status"].startswith(
                    "SKIPPED"
                )
                for r in results
            )

        except Exception as e:

            print(
                f"FAILED BID: {e}"
            )

            total_failed += 1

    print("\n")
    print("=" * 90)
    print("STAGE 02 COMPLETE")
    print("=" * 90)

    print(
        f"Completed documents: "
        f"{total_completed}"
    )

    print(
        f"Failed documents: "
        f"{total_failed}"
    )

    print(
        f"Skipped documents: "
        f"{total_skipped}"
    )

    print(
        f"Already complete BIDs: "
        f"{total_existing}"
    )

    print(
        f"\nData directory:\n"
        f"{OUTPUT_ROOT.resolve()}"
    )


if __name__ == "__main__":
    main()