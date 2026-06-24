import os
import shutil
import tempfile
import logging
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
import io
from typing import Dict, Any
import uvicorn
from dotenv import load_dotenv


# Ensure we import from the root project directory
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.extractor.pdf_parser import extract_references_from_pdf
from app.main import process_citations
from app.reporting.docx_generator import build_docx_report

# Load config
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("source_checker_server")

app = FastAPI(title="Literature Review Source Checker API")

TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 
    "reporting", 
    "templates"
)
INDEX_HTML_PATH = os.path.join(TEMPLATES_DIR, "index.html")

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """
    Serves the single-page application homepage.
    """
    if not os.path.exists(INDEX_HTML_PATH):
        raise HTTPException(
            status_code=504, 
            detail="index.html template not found in app/reporting/templates."
        )
        
    with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

@app.post("/upload")
async def handle_pdf_upload(file: UploadFile = File(...)):
    """
    Receives an academic paper PDF file, runs it through the verification pipeline,
    and returns the structured results as JSON.
    """
    # 1. Validate file format
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
        
    temp_pdf_path = None
    try:
        # 2. Save uploaded file to a temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            shutil.copyfileobj(file.file, tmp)
            temp_pdf_path = tmp.name
            
        logger.info(f"Received file: {file.filename}, saved to temporary path: {temp_pdf_path}")
        
        # 3. Extract citations
        try:
            citations = extract_references_from_pdf(temp_pdf_path)
        except Exception as e:
            logger.error(f"Error parsing PDF text: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to read/parse PDF text: {str(e)}")
            
        if not citations:
            return {
                "summary": {
                    "total_references": 0,
                    "verified": 0,
                    "legitimate_llm": 0,
                    "review_required": 0
                },
                "references": []
            }
            
        # 4. Asynchronously process citations against Crossref
        mailto_email = os.getenv("CROSSREF_MAILTO", "anonymous@example.com")
        cache_path = "cache/citation_cache.db"
        
        results = await process_citations(citations, mailto_email, cache_path)
        
        # 5. Calculate statistics summary
        summary = {
            "total_references": len(results),
            "verified": sum(1 for r in results if r["status"] == "VERIFIED"),
            "legitimate_llm": sum(1 for r in results if r["status"] == "LEGITIMATE_KNOWN"),
            "review_required": sum(1 for r in results if r["status"] == "REVIEW_REQUIRED")
        }
        
        return {
            "summary": summary,
            "references": results
        }
        
    except Exception as e:
        logger.exception("Server error during processing upload:")
        raise HTTPException(status_code=500, detail=f"An error occurred while checking references: {str(e)}")
        
    finally:
        # 6. Cleanup temporary file
        if temp_pdf_path and os.path.exists(temp_pdf_path):
            try:
                os.unlink(temp_pdf_path)
            except Exception as e:
                logger.error(f"Failed to delete temp file: {temp_pdf_path}, error: {e}")

@app.post("/export/docx")
async def export_docx(data: Dict[str, Any]):
    """
    Receives JSON verification results, builds a formatted DOCX document,
    and streams it back as a file download.
    """
    try:
        doc = build_docx_report(data)
        bio = io.BytesIO()
        doc.save(bio)
        bio.seek(0)
        return StreamingResponse(
            bio,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": "attachment; filename=verification_report.docx"}
        )
    except Exception as e:
        logger.exception("Failed to export DOCX report:")
        raise HTTPException(status_code=500, detail=f"Failed to generate Word document: {str(e)}")

if __name__ == "__main__":
    # If run directly, launch uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
