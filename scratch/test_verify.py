import asyncio
import os
import json
import sys
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.extractor.pdf_parser import extract_references_from_pdf
from app.main import process_citations

load_dotenv()

async def main():
    pdf_path = "Sample paper2.pdf"
    if not os.path.exists(pdf_path):
        print(f"File not found: {pdf_path}")
        return
        
    print("Extracting references...")
    citations = extract_references_from_pdf(pdf_path)
    print(f"Found {len(citations)} citations.")
    
    print("Running verification pipeline...")
    results = await process_citations(citations, "anonymous@example.com", "cache/citation_cache.db")
    
    # Save the raw results to a debug file
    debug_path = "cache/debug_results.json"
    with open(debug_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Saved results to: {debug_path}")
    
    # Print statistics
    summary = {
        "VERIFIED": 0,
        "FOUND_NO_DOI": 0,
        "REVIEW_REQUIRED": 0,
        "SUSPECTED_FAKE": 0,
        "NOT_FOUND": 0
    }
    for r in results:
        status = r["status"]
        summary[status] = summary.get(status, 0) + 1
        
    print("\nSummary Stats:")
    for status, count in summary.items():
        print(f"  {status}: {count}")
        
    # Print the suspected fakes
    print("\nSuspected Fakes Details:")
    count = 0
    for r in results:
        if r["status"] in ["SUSPECTED_FAKE", "NOT_FOUND"]:
            count += 1
            print(f"\n[{count}] Reference ID #{r['reference_id']}")
            print(f"  Raw: {r['raw_reference']}")
            if r.get('matched_metadata'):
                print(f"  Match Title: {r['matched_metadata']['title']}")
                print(f"  Match Authors: {r['matched_metadata']['authors']}")
            else:
                print("  No Match Metadata")
            if r.get('llm_verdict'):
                print(f"  LLM Verdict: {r['llm_verdict']}")
                
if __name__ == "__main__":
    asyncio.run(main())
