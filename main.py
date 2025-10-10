import os
import logging
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import docraptor
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="Proposal Backend API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Template configurations
TEMPLATES = [
    {
        "id": "proposal",
        "name": "Professional Proposal",
        "description": "Clean, professional design with Inter and Merriweather fonts",
        "pageSize": "US-Letter",
        "previewUrl": "https://images.unsplash.com/photo-1586281380349-632531db7ed4?w=400&h=300&fit=crop"
    },
    {
        "id": "modern-tech",
        "name": "Modern Tech",
        "description": "Contemporary tech-focused layout with bold typography",
        "pageSize": "US-Letter",
        "previewUrl": "https://images.unsplash.com/photo-1553877522-43269d4ea984?w=400&h=300&fit=crop"
    },
    {
        "id": "docraptor-usletter",
        "name": "DocRaptor Professional (US Letter)",
        "description": "Full-featured design with cover page, headers, and cyan accents",
        "pageSize": "US-Letter",
        "previewUrl": "https://images.unsplash.com/photo-1568792923760-d70635a89fdc?w=400&h=300&fit=crop"
    },
    {
        "id": "docraptor-a4",
        "name": "DocRaptor Professional (A4)",
        "description": "Full-featured design with cover page, headers, and cyan accents",
        "pageSize": "A4",
        "previewUrl": "https://images.unsplash.com/photo-1568792923760-d70635a89fdc?w=400&h=300&fit=crop"
    }
]

# Request models
class ExportOptions(BaseModel):
    pageSize: str = "US-Letter"
    test: bool = False

class GeneratePDFRequest(BaseModel):
    html: str
    templateId: str
    options: Optional[ExportOptions] = None

class GeneratePreviewRequest(BaseModel):
    html: str
    templateId: str
    pages: int = 2

# Environment configuration
DOCRAPTOR_API_KEY = os.getenv("DOCRAPTOR_API_KEY") or os.getenv("DOCRAPTOR_API_TOKEN") or ""
DOCRAPTOR_TEST_MODE = os.getenv("DOCRAPTOR_TEST_MODE", "false").lower() == "true"

# Log configuration at startup (never log the actual key)
if not DOCRAPTOR_API_KEY:
    logger.error("[PDF] DocRaptor API key missing (set DOCRAPTOR_API_KEY)")
else:
    logger.info(f"[PDF] DocRaptor key configured: {bool(DOCRAPTOR_API_KEY)}")
    logger.info(f"[PDF] DocRaptor test mode: {DOCRAPTOR_TEST_MODE}")

# DocRaptor client initialization
def get_docraptor_client():
    """Initialize DocRaptor client with proper authentication"""
    if not DOCRAPTOR_API_KEY:
        raise HTTPException(status_code=500, detail="DocRaptor API key not configured")
    
    # CRITICAL: Must set username on api_client.configuration, not on docraptor.configuration
    doc_api = docraptor.DocApi()
    doc_api.api_client.configuration.username = DOCRAPTOR_API_KEY
    
    return doc_api

# Load template CSS (for non-wrapper templates)
def load_template_css(template_id: str, page_size: str = "US-Letter") -> str:
    """Load CSS for a template"""
    try:
        css_filename = f"style.{template_id}.css"
        css_path = os.path.join(os.path.dirname(__file__), "templates", css_filename)
        
        if not os.path.exists(css_path):
            logger.warning(f"CSS file not found: {css_path}, using empty CSS")
            return ""
        
        with open(css_path, 'r') as f:
            css = f.read()
        
        logger.info(f"Loading CSS from: {css_path}")
        return css
    except Exception as e:
        logger.error(f"Error loading CSS: {str(e)}")
        return ""

# Load DocRaptor wrapper template
def load_docraptor_wrapper(template_id: str) -> tuple[str, str]:
    """Load wrapper HTML and CSS for DocRaptor templates
    
    Returns:
        tuple: (wrapper_html, css_content)
    """
    try:
        # Determine folder based on template ID
        if template_id == "docraptor-usletter":
            folder = "usletter"
        elif template_id == "docraptor-a4":
            folder = "a4"
        else:
            raise ValueError(f"Unknown DocRaptor template: {template_id}")
        
        # Construct paths
        base_path = os.path.join(os.path.dirname(__file__), "templates", "docraptor", folder)
        wrapper_path = os.path.join(base_path, "wrapper.html")
        css_path = os.path.join(base_path, "style.css")
        
        # Load wrapper HTML
        if not os.path.exists(wrapper_path):
            raise FileNotFoundError(f"Wrapper HTML not found: {wrapper_path}")
        
        with open(wrapper_path, 'r', encoding='utf-8') as f:
            wrapper_html = f.read()
        
        # Load CSS
        if not os.path.exists(css_path):
            raise FileNotFoundError(f"CSS file not found: {css_path}")
        
        with open(css_path, 'r', encoding='utf-8') as f:
            css_content = f.read()
        
        logger.info(f"Loaded DocRaptor wrapper from: {base_path}")
        logger.info(f"Wrapper HTML length: {len(wrapper_html)} chars")
        logger.info(f"CSS length: {len(css_content)} chars")
        
        return wrapper_html, css_content
        
    except Exception as e:
        logger.error(f"Error loading DocRaptor wrapper: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to load template: {str(e)}")

# Extract content from Supabase HTML
def extract_proposal_content(html: str) -> dict:
    """Extract sections and metadata from Supabase-generated HTML
    
    Returns:
        dict: Contains 'title', 'sections', 'date'
    """
    try:
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract title (first h1)
        title_el = soup.select_one('h1')
        title = title_el.get_text(strip=True) if title_el else 'Proposal'
        
        # Extract all sections with class 'section'
        sections = soup.select('div.section, .section')
        
        # If no sections found, try to extract main content
        if not sections:
            # Try to find any content divs
            sections = soup.select('div.document-page > div, main > div')
        
        # Convert sections to HTML strings and wrap in chapter divs
        section_html_list = []
        for i, section in enumerate(sections):
            # Wrap each section in a .chapter div for DocRaptor styling
            section_str = str(section)
            
            # Add chapter class if not present
            if 'class="chapter"' not in section_str and 'class="section"' in section_str:
                section_str = section_str.replace('class="section"', 'class="chapter"')
            elif 'class=' not in section_str:
                section_str = f'<div class="chapter">{section_str}</div>'
            
            section_html_list.append(section_str)
        
        content_html = "\n".join(section_html_list)
        
        # Get current date
        date = datetime.now().strftime("%m.%d.%y")
        
        logger.info(f"Extracted title: {title}")
        logger.info(f"Extracted {len(section_html_list)} sections")
        logger.info(f"Content HTML length: {len(content_html)} chars")
        
        return {
            'title': title,
            'sections': content_html,
            'date': date
        }
        
    except Exception as e:
        logger.error(f"Error extracting proposal content: {str(e)}")
        raise

# Inject content into wrapper
def inject_content_into_wrapper(wrapper_html: str, css: str, content: dict) -> str:
    """Replace placeholders in wrapper with actual content
    
    Args:
        wrapper_html: The wrapper HTML template
        css: The CSS content to inject
        content: Dictionary with 'title', 'sections', 'date'
    
    Returns:
        str: Final HTML ready for DocRaptor
    """
    try:
        # Default placeholder values
        defaults = {
            '{{DOCUMENT_TITLE}}': content.get('title', 'Proposal'),
            '{{DOCUMENT_DATE}}': content.get('date', datetime.now().strftime("%m.%d.%y")),
            '{{CLIENT_NAME}}': 'Client Name',
            '{{LOGO_TEXT}}': 'Logo & Company Name',
            '{{FOOTER_CONTACT}}': '317.234.8765 | email@company.com | companywebsite.com',
            '{{COMPANY_WEBSITE}}': 'companywebsite.com',
            '{{COMPANY_EMAIL}}': 'email@company.com',
            '{{COMPANY_PHONE}}': '317.213.2345',
            '{{TEMPLATE_CSS}}': css,
            '{{PROPOSAL_CONTENT}}': content.get('sections', '')
        }
        
        # Replace all placeholders
        final_html = wrapper_html
        for placeholder, value in defaults.items():
            final_html = final_html.replace(placeholder, value)
        
        logger.info(f"Final HTML length: {len(final_html)} chars")
        logger.info(f"CSS injected: {'{{TEMPLATE_CSS}}' not in final_html}")
        logger.info(f"Content injected: {'{{PROPOSAL_CONTENT}}' not in final_html}")
        
        return final_html
        
    except Exception as e:
        logger.error(f"Error injecting content into wrapper: {str(e)}")
        raise

# Inject CSS into HTML (for non-wrapper templates)
def inject_css_into_html(html: str, css: str) -> str:
    """Inject CSS into HTML <head> section"""
    if not css:
        return html
    
    css_tag = f"<style>\n{css}\n</style>"
    
    if "<head>" in html:
        return html.replace("<head>", f"<head>\n{css_tag}")
    else:
        return f"<html><head>{css_tag}</head><body>{html}</body></html>"

# Root endpoint
@app.get("/")
async def root():
    return {"status": "ok", "message": "Proposal Backend API"}

# Health check
@app.get("/health")
async def health():
    return {"status": "healthy"}

# Get available templates
@app.get("/api/v1/templates")
async def get_templates():
    logger.info(f"Returning {len(TEMPLATES)} templates")
    return TEMPLATES

# Diagnostic endpoint for DocRaptor configuration
@app.get("/api/v1/diag/docraptor")
async def docraptor_diagnostics():
    """Check DocRaptor configuration without exposing sensitive data"""
    try:
        # Check if client can be initialized
        doc_api = get_docraptor_client()
        sdk_username_set = bool(doc_api.api_client.configuration.username)
    except Exception as e:
        sdk_username_set = False
    
    return {
        "key_present": bool(DOCRAPTOR_API_KEY),
        "key_length": len(DOCRAPTOR_API_KEY) if DOCRAPTOR_API_KEY else 0,
        "test_mode": DOCRAPTOR_TEST_MODE,
        "sdk_username_set": sdk_username_set,
        "status": "configured" if DOCRAPTOR_API_KEY and sdk_username_set else "missing_config"
    }

# Generate PDF
@app.post("/api/v1/generate-pdf")
async def generate_pdf(request: GeneratePDFRequest):
    try:
        logger.info(f"Generating PDF with template: {request.templateId}")
        
        # Check if this is a DocRaptor wrapper template
        if request.templateId.startswith("docraptor-"):
            # Use wrapper approach
            logger.info("Using DocRaptor wrapper approach")
            
            # Load wrapper and CSS
            wrapper_html, css = load_docraptor_wrapper(request.templateId)
            
            # Extract content from Supabase HTML
            content = extract_proposal_content(request.html)
            
            # Inject content into wrapper
            final_html = inject_content_into_wrapper(wrapper_html, css, content)
            
        else:
            # Use traditional CSS injection approach
            logger.info("Using traditional CSS injection approach")
            
            # Load template CSS
            css = load_template_css(
                request.templateId,
                request.options.pageSize if request.options else "US-Letter"
            )
            
            # Inject CSS into HTML
            final_html = inject_css_into_html(request.html, css)
            
            # Debug logging
            logger.info(f"[DEBUG] ✓ CSS loaded successfully")
            logger.info(f"[DEBUG] CSS length: {len(css)} characters")
            if css:
                logger.info(f"[DEBUG] CSS starts with: {css[:200]}")
            logger.info(f"[DEBUG] Original HTML length: {len(request.html)}")
            logger.info(f"[DEBUG] Styled HTML length: {len(final_html)}")
            logger.info(f"[DEBUG] Contains <style> tag: {'<style>' in final_html}")
        
        # Initialize DocRaptor client
        doc_api = get_docraptor_client()
        
        # Generate PDF
        logger.info("Calling DocRaptor API...")
        logger.info(f"[PDF] Request details - test_mode={DOCRAPTOR_TEST_MODE}, key_present={bool(DOCRAPTOR_API_KEY)}")
        
        pdf_response = doc_api.create_doc({
            "document_content": final_html,
            "name": "proposal.pdf",
            "document_type": "pdf",
            "test": DOCRAPTOR_TEST_MODE,
            "prince_options": {
                "media": "print",
                "profile": "PDF/A-1b",
            }
        })
        
        logger.info("PDF generated successfully")
        
        return Response(
            content=pdf_response,
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename=proposal.pdf"
            }
        )
        
    except docraptor.rest.ApiException as e:
        status = getattr(e, 'status', None)
        logger.error(f"DocRaptor API error: status={status}, key_present={bool(DOCRAPTOR_API_KEY)}, test_mode={DOCRAPTOR_TEST_MODE}")
        logger.error(f"DocRaptor error details: {str(e)}")
        
        # Return clear error to frontend
        if status == 401:
            raise HTTPException(
                status_code=502,
                detail="PDF service authentication failed. Please check DocRaptor API key configuration."
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=f"DocRaptor error: {e.body if hasattr(e, 'body') else str(e)}"
            )
    except Exception as e:
        logger.error(f"Error generating PDF: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Generate preview
@app.post("/api/v1/generate-preview")
async def generate_preview(request: GeneratePreviewRequest):
    try:
        logger.info(f"Generating preview with template: {request.templateId} ({request.pages} pages)")
        
        # Check if this is a DocRaptor wrapper template
        if request.templateId.startswith("docraptor-"):
            # Use wrapper approach
            logger.info("Using DocRaptor wrapper approach for preview")
            
            # Load wrapper and CSS
            wrapper_html, css = load_docraptor_wrapper(request.templateId)
            
            # Extract content from Supabase HTML
            content = extract_proposal_content(request.html)
            
            # Inject content into wrapper
            final_html = inject_content_into_wrapper(wrapper_html, css, content)
            
        else:
            # Use traditional CSS injection approach
            logger.info("Using traditional CSS injection for preview")
            
            # Load template CSS
            css = load_template_css(request.templateId)
            logger.info(f"Loading CSS from: /opt/render/project/src/templates/style.{request.templateId}.css")
            
            # Inject CSS into HTML
            final_html = inject_css_into_html(request.html, css)
        
        # Initialize DocRaptor client
        doc_api = get_docraptor_client()
        
        # Generate preview
        logger.info("Calling DocRaptor API for preview...")
        pdf_response = doc_api.create_doc({
            "document_content": final_html,
            "name": "preview.pdf",
            "document_type": "pdf",
            "test": True,
            "prince_options": {
                "media": "print",
            }
        })
        
        logger.info("Preview generated successfully")
        
        return Response(
            content=pdf_response,
            media_type="application/pdf",
            headers={
                "Content-Disposition": "inline; filename=preview.pdf"
            }
        )
        
    except docraptor.rest.ApiException as e:
        status = getattr(e, 'status', None)
        logger.error(f"DocRaptor API error (preview): status={status}, key_present={bool(DOCRAPTOR_API_KEY)}, test_mode=True")
        logger.error(f"DocRaptor error details: {str(e)}")
        
        # Return clear error to frontend
        if status == 401:
            raise HTTPException(
                status_code=502,
                detail="PDF preview authentication failed. Please check DocRaptor API key configuration."
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=f"DocRaptor error: {e.body if hasattr(e, 'body') else str(e)}"
            )
    except Exception as e:
        logger.error(f"Error generating preview: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Error handlers
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return Response(
        content='{"error": "Not found"}',
        status_code=404,
        media_type="application/json"
    )

@app.exception_handler(500)
async def internal_error_handler(request, exc):
    logger.error(f"Internal error: {str(exc)}")
    return Response(
        content='{"error": "Internal server error"}',
        status_code=500,
        media_type="application/json"
    )

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
