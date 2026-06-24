import os
import sys
import argparse
import asyncio
import logging
from typing import List, Dict, Any

from dotenv import load_dotenv

# Add the project root directory to the python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.extractor.pdf_parser import extract_references_from_pdf
from app.extractor.docx_parser import extract_references_from_docx
from app.normalizer.reference_cleaner import clean_reference
from app.verifier.crossref_client import CrossrefClient
from app.verifier.matcher import verify_reference
from app.reporting.report_generator import generate_report

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("reference_verifier")

async def process_citations(
    citations: List[Dict[str, Any]], 
    mailto: str, 
    cache_path: str
) -> List[Dict[str, Any]]:
    """
    Asynchronously queries Crossref and validates all citations.
    """
    client = CrossrefClient(mailto=mailto, cache_db_path=cache_path)
    semaphore = asyncio.Semaphore(5)
    
    async def process_single(cit: Dict[str, Any]) -> Dict[str, Any]:
        async with semaphore:
            raw_ref = cit["raw_reference"]
            normalized_ref = clean_reference(raw_ref)
            
            # Query Crossref API
            candidates = await client.query_reference(normalized_ref)
            
            # Verify and classify match
            verification = await verify_reference(raw_ref, candidates)
            
            return {
                "reference_id": cit["reference_id"],
                "raw_reference": raw_ref,
                "normalized_reference": normalized_ref,
                "status": verification["status"],
                "confidence": verification["confidence"],
                "matched_metadata": verification["matched_metadata"],
                "llm_verdict": verification["llm_verdict"]
            }
        
    # Process all citations concurrently
    tasks = [process_single(cit) for cit in citations]
    results = await asyncio.gather(*tasks)

    # Sort results: REVIEW_REQUIRED -> LEGITIMATE_KNOWN -> VERIFIED
    status_priority = {
        "REVIEW_REQUIRED": 0,
        "LEGITIMATE_KNOWN": 1,
        "VERIFIED": 2
    }
    results_list = list(results)
    results_list.sort(key=lambda r: status_priority.get(r["status"], 99))
    return results_list



def main():
    parser = argparse.ArgumentParser(
        description="Verify research paper references using the Crossref API."
    )
    parser.add_argument(
        "-f", "--file", 
        required=True, 
        help="Path to the research paper PDF or raw citation text file."
    )
    parser.add_argument(
        "--mailto", 
        help="Contact email to access Crossref Polite Pool (defaults to CROSSREF_MAILTO in .env)."
    )
    parser.add_argument(
        "--cache", 
        default="cache/citation_cache.db", 
        help="Path to SQLite cache database (default: cache/citation_cache.db)."
    )
    parser.add_argument(
        "-o", "--output-dir", 
        default="outputs", 
        help="Directory to save JSON and HTML reports (default: outputs)."
    )
    
    args = parser.parse_args()
    
    if not os.path.exists(args.file):
        logger.error(f"Input file not found: {args.file}")
        sys.exit(1)
        
    # 1. Extraction phase
    citations = []
    file_ext = os.path.splitext(args.file)[1].lower()
    
    if file_ext == ".pdf":
        logger.info(f"Analyzing PDF: {args.file}")
        try:
            citations = extract_references_from_pdf(args.file)
        except Exception as e:
            logger.error(f"Failed to read/parse PDF: {e}")
            sys.exit(1)
    elif file_ext == ".docx":
        logger.info(f"Analyzing Word document: {args.file}")
        try:
            citations = extract_references_from_docx(args.file)
        except Exception as e:
            logger.error(f"Failed to read/parse Word document: {e}")
            sys.exit(1)
    else:
        # Treat as plain text file with one citation per line
        logger.info(f"Reading text file: {args.file}")
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]
            for idx, line in enumerate(lines, start=1):
                citations.append({
                    "reference_id": idx,
                    "raw_reference": line
                })
        except Exception as e:
            logger.error(f"Failed to read text file: {e}")
            sys.exit(1)
            
    if not citations:
        logger.warning("No references found in the input file.")
        sys.exit(0)
        
    logger.info(f"Extracted {len(citations)} citations. Beginning verification phase...")
    
    # 2. Verification phase
    mailto_email = args.mailto or os.getenv("CROSSREF_MAILTO") or "anonymous@example.com"
    
    # Run async event loop
    try:
        results = asyncio.run(process_citations(citations, mailto_email, args.cache))
    except Exception as e:
        logger.error(f"An error occurred during verification: {e}")
        sys.exit(1)
        
    # 3. Aggregate statistics
    summary = {
        "total_references": len(results),
        "verified": sum(1 for r in results if r["status"] == "VERIFIED"),
        "legitimate_llm": sum(1 for r in results if r["status"] == "LEGITIMATE_KNOWN"),
        "review_required": sum(1 for r in results if r["status"] == "REVIEW_REQUIRED")
    }
    
    report_data = {
        "summary": summary,
        "references": results
    }
    
    # 4. Report generation
    generate_report(report_data, args.output_dir)
    
    logger.info("Verification Complete!")
    logger.info(f"Summary: {summary['verified']} Legitimate, {summary['legitimate_llm']} Legitimate (LLM), {summary['review_required']} Review Required.")
    logger.info(f"View report dashboard at: {os.path.abspath(os.path.join(args.output_dir, 'report.html'))}")

if __name__ == "__main__":
    main()
