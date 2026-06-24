import re

def clean_reference(raw_ref: str) -> str:
    """
    Cleans and normalizes a raw citation/reference string to optimize it for Crossref API queries.
    
    Tasks performed:
    1. Removes line breaks and collapses multiple spaces.
    2. Removes leading numbering prefixes like [1], 1., (1), or 1. 
    3. Trims leading/trailing whitespace.
    """
    if not raw_ref:
        return ""
    
    # 1. Replace newlines, carriage returns, and tabs with single spaces
    cleaned = re.sub(r'[\r\n\t]+', ' ', raw_ref)
    
    # Collapse multiple consecutive spaces
    cleaned = re.sub(r'\s+', ' ', cleaned)
    
    # Trim leading/trailing whitespace before parsing prefix
    cleaned = cleaned.strip()
    
    # 2. Strip leading citation indicators:
    # Matches patterns like: "[12]", "12.", "(12)", "12 ", "Ref 12." at the beginning
    # Examples:
    # "[1] Smith et al." -> "Smith et al."
    # "12. Jones, A." -> "Jones, A."
    # "(3) Brown, B." -> "Brown, B."
    # "14 Smith, C." -> "Smith, C."
    prefix_patterns = [
        r'^\[\d+\]\s*',              # [1] or [12]
        r'^\(\d+\)\s*',              # (1) or (12)
        r'^\d+\.\s+',                # 1. or 12.
        r'^\d+\s+(?=[A-Z])',         # 1 Smith (number followed by capital letter)
        r'^(?:Ref|Reference)\s*\d+[\.:\s]\s*' # Ref 1., Reference 12:
    ]
    
    for pattern in prefix_patterns:
        cleaned_temp = re.sub(pattern, '', cleaned, count=1)
        if cleaned_temp != cleaned:
            cleaned = cleaned_temp
            break
            
    # Final trim
    cleaned = cleaned.strip()
    
    return cleaned
