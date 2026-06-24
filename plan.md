# Reference Verification System - Implementation Plan

## Objective

Build a system that analyzes a research paper PDF and verifies whether each reference:

1. Exists in a scholarly database.
2. Has a valid DOI.
3. Matches the cited metadata with high confidence.

The system is intended as a lightweight citation validation tool rather than a full academic quality assessment platform.

---

# Scope

## In Scope

* PDF ingestion
* Reference extraction
* Reference normalization
* Crossref lookup
* DOI verification
* Confidence scoring
* Verification report generation

## Out of Scope (Future Enhancements)

* Retraction detection
* Citation count analysis
* Scopus indexing verification
* Web of Science verification
* Predatory journal detection
* Full-text retrieval

---

# High-Level Architecture

```text
PDF Research Paper
        │
        ▼
Reference Extraction
        │
        ▼
Reference Normalization
        │
        ▼
Crossref Lookup
        │
        ▼
Metadata Validation
        │
        ├── Reference Exists?
        ├── DOI Present?
        └── Confidence Score
        │
        ▼
Verification Report
```

---

# Technology Stack

## Language

```text
Python 3.12+
```

## Libraries

### PDF Processing

```text
GROBID
PyMuPDF
```

### Matching

```text
RapidFuzz
```

### HTTP Requests

```text
httpx
```

### Concurrency

```text
asyncio
```

### Output

```text
JSON
```

---

# Component 1: PDF Ingestion

## Input

```text
paper.pdf
```

The system accepts a research paper PDF as input.

## Output

```text
Raw PDF content
```

---

# Component 2: Reference Extraction

## Preferred Method

Use GROBID to extract references from the bibliography section.

### Output

```json
[
  {
    "reference_id": 1,
    "raw_reference": "Smith J. Deep Learning Applications..."
  }
]
```

## Fallback Method

If GROBID fails:

1. Extract text using PyMuPDF.
2. Locate the References/Bibliography section.
3. Split individual references using heuristics.

---

# Component 3: Reference Normalization

Normalize extracted references before lookup.

## Cleaning Rules

* Remove line breaks
* Collapse multiple spaces
* Remove numbering prefixes
* Remove citation markers
* Standardize punctuation spacing

### Example

Input:

```text
[12] Smith J.
Deep Learning Applications
Journal of AI
```

Output:

```text
Smith J. Deep Learning Applications Journal of AI
```

## Stored Structure

```json
{
  "reference_id": 12,
  "raw_reference": "...",
  "normalized_reference": "..."
}
```

---

# Component 4: Crossref Resolution

For each normalized reference:

```http
GET https://api.crossref.org/works?query.bibliographic=<reference>
```

Retrieve the highest-confidence candidate.

## Extracted Metadata

```json
{
  "title": "...",
  "authors": [...],
  "year": 2024,
  "doi": "...",
  "score": 97.8
}
```

---

# Component 5: Match Validation

Crossref's score should not be trusted blindly.

Additional validation is performed using metadata similarity.

## Title Similarity

Compare:

```text
Extracted Title
```

vs

```text
Crossref Title
```

Using:

```python
rapidfuzz.fuzz.token_set_ratio()
```

---

## Author Similarity

Compare author lists.

Example:

```text
Smith, Johnson
```

vs

```text
Smith, Johnson, Brown
```

Generate an author similarity score.

---

## Year Similarity

Compare publication years.

Rules:

```text
Exact Match      → Full Score
±1 Year          → Small Penalty
>1 Year Difference → Larger Penalty
```

---

## Confidence Calculation

```python
confidence =
0.70 * title_similarity +
0.20 * author_similarity +
0.10 * year_similarity
```

Scale:

```text
0-100
```

---

# Component 6: Classification

## VERIFIED

Conditions:

```text
confidence >= 85
AND DOI exists
```

Output:

```json
{
  "status": "VERIFIED",
  "doi": "10.xxxx/xxxx"
}
```

---

## FOUND_NO_DOI

Conditions:

```text
confidence >= 85
AND DOI missing
```

Output:

```json
{
  "status": "FOUND_NO_DOI"
}
```

---

## REVIEW_REQUIRED

Conditions:

```text
60 <= confidence < 85
```

Output:

```json
{
  "status": "REVIEW_REQUIRED"
}
```

---

## NOT_FOUND

Conditions:

```text
confidence < 60
```

Output:

```json
{
  "status": "NOT_FOUND"
}
```

---

# Component 7: Report Generation

Generate a structured JSON report.

## Summary

```json
{
  "total_references": 42,
  "verified": 35,
  "found_no_doi": 4,
  "review_required": 2,
  "not_found": 1
}
```

## Detailed Results

```json
{
  "reference_id": 1,
  "status": "VERIFIED",
  "confidence": 97,
  "doi": "10.xxxx/xxxx"
}
```

---

# Output Example

```json
{
  "summary": {
    "total_references": 42,
    "verified": 35,
    "found_no_doi": 4,
    "review_required": 2,
    "not_found": 1
  },
  "references": [
    {
      "reference_id": 1,
      "status": "VERIFIED",
      "confidence": 97,
      "doi": "10.xxxx/xxxx"
    }
  ]
}
```

---

# Performance Strategy

## Parallel Crossref Requests

Use asynchronous execution:

```python
asyncio + httpx
```

Expected performance:

```text
50 References

Sequential Processing: 50-100 seconds
Parallel Processing: 3-8 seconds
```

---

# Caching Strategy

Cache Crossref responses using a hash of the normalized reference.

## Cache Structure

```json
{
  "reference_hash": {
    "doi": "...",
    "metadata": "...",
    "confidence": 97
  }
}
```

Benefits:

* Reduced API calls
* Faster repeat processing
* Lower network dependency

---

# Project Structure

```text
reference-verifier/
│
├── app/
│   ├── extractor/
│   │   ├── grobid.py
│   │   └── pdf_parser.py
│   │
│   ├── normalizer/
│   │   └── reference_cleaner.py
│   │
│   ├── verifier/
│   │   ├── crossref_client.py
│   │   ├── matcher.py
│   │   └── scorer.py
│   │
│   ├── reporting/
│   │   └── report_generator.py
│   │
│   └── main.py
│
├── cache/
│
├── outputs/
│
├── tests/
│
└── requirements.txt
```

---

# Success Criteria

The system should:

* Extract references from standard academic PDFs.
* Resolve references through Crossref.
* Verify existence of cited works.
* Verify DOI availability.
* Produce confidence-scored results.
* Generate a machine-readable verification report.
* Process typical research papers in under 10 seconds.

---

# MVP Deliverable

Version 1.0 should provide:

✓ PDF Upload

✓ Reference Extraction

✓ Crossref Verification

✓ DOI Detection

✓ Confidence Scoring

✓ JSON Report Generation

No additional academic quality metrics are required for the initial release.
