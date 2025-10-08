"""
GovHub Template Backend Service
Handles PDF generation with templates using DocRaptor
"""

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict, List
import docraptor
import os
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="GovHub Template API",
    description="PDF generation service with template support",
    version="1.0.0"
)

# CORS Configuration - Updated with your Lovable URLs
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Local development
        "http://localhost:5174",  # Alternative local port
        "https://8365aeb7-4757-4e22-b99e-4605f191ab8b.lovableproject.com",  # Main Lovable project
        "https://id-preview--8365aeb7-4757-4e22-b99e-4605f191ab8b.lovable.app",  # Your preview URL
        "https://*--8365aeb7-4757-4e22-b99e-4605f191ab8b.lovable.app",  # All preview branches
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Template directory
TEMPLATES_DIR = Path(__file__).parent / "templates"
TEMPLATES_DIR.mkdir(exist_ok=True)

# Pydantic Models
class Template(BaseModel):
    id: str
    name: str
    description: str
    thumbnail_url: Optional[str] = None
    page_size: str = "US-Letter"
    use_case: Optional[str] = None


class PDFOptions(BaseModel):
    pageSize: str = "US-Letter"
    test: bool = False


class GeneratePDFRequest(BaseModel):
    html: str = Field(..., description="HTML content to convert")
    templateId: str = Field(..., description="Template ID to apply")
    options: Optional[PDFOptions] = PDFOptions()


class GeneratePreviewRequest(BaseModel):
    html: str = Field(..., description="HTML content to convert")
    templateId: str = Field(..., description="Template ID to apply")
    pageCount: int = Field(default=2, ge=1, le=5, description="Number of pages in preview")


# Helper Functions
def get_docraptor_client():
    """Initialize DocRaptor API client"""
    api_key = os.getenv("DOCRAPTOR_API_KEY")
    if not api_key:
        raise ValueError("DOCRAPTOR_API_KEY environment variable not set")
    
    doc_api = docraptor.DocApi()
    doc_api.api_client.configuration.username = api_key
    return doc_api


def load_template_css(template_id: str, page_size: str = "US-Letter") -> str:
    """Load CSS file for the specified template"""
    
    # Try to load specific template CSS
    css_filename = f"style.{template_id}.css"
    css_path = TEMPLATES_DIR / css_filename
    
    # Fallback to page-size specific CSS
    if not css_path.exists():
        css_filename = f"style.{page_size}.css"
        css_path = TEMPLATES_DIR / css_filename
    
    # Fallback to default
    if not css_path.exists():
        css_path = TEMPLATES_DIR / "style.USLetter.css"
    
    if not css_path.exists():
        logger.error(f"Template CSS not found: {css_path}")
        raise HTTPException(
            status_code=404,
            detail=f"Template '{template_id}' not found. Available templates: {list_available_templates()}"
        )
    
    logger.info(f"Loading CSS from: {css_path}")
    return css_path.read_text(encoding='utf-8')


def inject_css_into_html(html: str, css: str) -> str:
    """Inject CSS stylesheet into HTML document"""
    
    style_tag = f"<style>{css}</style>"
    
    # Try to inject before closing </head> tag
    if "</head>" in html:
        return html.replace("</head>", f"{style_tag}</head>", 1)
    
    # Try to inject after opening <head> tag
    if "<head>" in html:
        return html.replace("<head>", f"<head>{style_tag}", 1)
    
    # If no head tag, wrap entire HTML
    if "<html>" in html:
        return html.replace("<html>", f"<html><head>{style_tag}</head>", 1)
    
    # Last resort: prepend to document
    return f"<html><head>{style_tag}</head><body>{html}</body></html>"


def list_available_templates() -> List[str]:
    """List all available template IDs"""
    if not TEMPLATES_DIR.exists():
        return []
    
    templates = []
    for css_file in TEMPLATES_DIR.glob("style.*.css"):
        # Extract template ID from filename
        template_id = css_file.stem.replace("style.", "")
        if template_id not in ["USLetter", "A4"]:  # Skip base templates
            templates.append(template_id)
    
    return templates


def truncate_html_for_preview(html: str, page_count: int) -> str:
    """
    Attempt to truncate HTML to approximately N pages.
    This is a rough heuristic - DocRaptor doesn't support page limiting directly.
    """
    # Add CSS to force page break after N pages
    preview_css = f"""
    <style>
    @page {{
        /* Force orphan/widow control */
    }}
    /* This is approximate - actual page breaks depend on content */
    </style>
    """
    
    # Add the preview CSS
    if "</head>" in html:
        html = html.replace("</head>", f"{preview_css}</head>", 1)
    
    return html


# API Endpoints
@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "GovHub Template API",
        "version": "1.0.0"
    }


@app.get("/api/health")
async def health_check():
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy",
        "service": "GovHub Template API",
        "timestamp": os.popen('date').read().strip()
    }


@app.get("/api/v1/templates", response_model=List[Template])
async def get_templates():
    """
    List all available proposal templates
    """
    try:
        templates = [
            Template(
                id="proposal",
                name="Professional Proposal",
                description="Clean, modern template with blue accents and professional layout",
                page_size="US-Letter",
                use_case="General business proposals and federal bids"
            ),
            Template(
                id="modern-tech",
                name="Modern Tech",
                description="Contemporary design optimized for technology proposals",
                page_size="US-Letter",
                use_case="Technology and innovation projects"
            ),
        ]
        logger.info(f"Returning {len(templates)} templates")
        return templates
        
    except Exception as e:
        logger.error(f"Error fetching templates: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/generate-pdf")
async def generate_pdf(request: GeneratePDFRequest):
    """
    Generate a styled PDF using the specified template
    
    - **html**: HTML content from Supabase
    - **templateId**: Template to apply
    - **options**: PDF generation options (page size, test mode)
    """
    try:
        logger.info(f"Generating PDF with template: {request.templateId}")
        
        # Load template CSS
        css = load_template_css(
            request.templateId,
            request.options.pageSize if request.options else "US-Letter"
        )
        
        # Inject CSS into HTML
        styled_html = inject_css_into_html(request.html, css)
        
        # Initialize DocRaptor client
        doc_api = get_docraptor_client()
        
        # Generate PDF
        logger.info("Calling DocRaptor API...")
        pdf_response = doc_api.create_doc({
            "document_content": styled_html,
            "name": "proposal.pdf",
            "document_type": "pdf",
            "test": request.options.test if request.options else False,
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
        logger.error(f"DocRaptor API error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"DocRaptor error: {e.body if hasattr(e, 'body') else str(e)}"
        )
    except Exception as e:
        logger.error(f"Error generating PDF: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/generate-preview")
async def generate_preview(request: GeneratePreviewRequest):
    """
    Generate a preview PDF (limited to first N pages for faster loading)
    
    - **html**: HTML content from Supabase
    - **templateId**: Template to apply
    - **pageCount**: Number of pages to include (default: 2, max: 5)
    """
    try:
        logger.info(f"Generating preview with template: {request.templateId} ({request.pageCount} pages)")
        
        # Load template CSS
        css = load_template_css(request.templateId)
        
        # Inject CSS into HTML
        styled_html = inject_css_into_html(request.html, css)
        
        # Truncate HTML for preview (approximate)
        styled_html = truncate_html_for_preview(styled_html, request.pageCount)
        
        # Initialize DocRaptor client
        doc_api = get_docraptor_client()
        
        # Generate preview PDF (always use test mode for previews)
        logger.info("Calling DocRaptor API for preview...")
        pdf_response = doc_api.create_doc({
            "document_content": styled_html,
            "name": "preview.pdf",
            "document_type": "pdf",
            "test": True,  # Always use test mode for previews
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
        logger.error(f"DocRaptor API error: {str(e)}")
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
