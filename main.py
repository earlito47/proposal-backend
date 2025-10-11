"""
GovHub Proposal Backend - FastAPI Application
Handles PDF/DOCX export with template styling and metadata injection
"""
import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
import docraptor
from bs4 import BeautifulSoup
from supabase import create_client, Client

# Import our custom modules
from src.metadata_extractor import (
    extract_metadata_from_html,
    extract_toc_from_html,
    generate_appendix_list_html
)
from src.pdf_merger import PDFMerger

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="GovHub Proposal Backend", version="2.0.0")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Supabase client (for PDF merging)
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY')

if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    logger.info("✓ Supabase client initialized")
else:
    logger.warning("⚠ Supabase credentials not found - PDF merging disabled")
    supabase = None


# ============================================================================
# Pydantic Models
# ============================================================================

class PDFOptions(BaseModel):
    """Options for PDF generation"""
    pageSize: str = "US-Letter"
    test: bool = False
    includeAppendices: bool = False  # Flag for PDF merging


class GeneratePDFRequest(BaseModel):
    """Request model for PDF generation"""
    html: str
    templateId: str
    options: Optional[PDFOptions] = None
    metadata: Optional[Dict[str, Any]] = None  # Includes proposalId, client info, etc.


# ============================================================================
# Template Management
# ============================================================================

def load_template_css(template_id: str, page_size: str = "US-Letter") -> str:
    """Load CSS for a specific template"""
    try:
        page_size_folder = page_size.lower().replace("-", "")  # "US-Letter" -> "usletter"
        css_path = Path(f"templates/docraptor/{page_size_folder}/style.css")
        
        if not css_path.exists():
            logger.warning(f"[Template CSS] File not found: {css_path}")
            return ""
        
        with open(css_path, 'r', encoding='utf-8') as f:
            css = f.read()
        
        logger.info(f"[Template CSS] ✓ Loaded {len(css)} characters from {css_path}")
        return css
        
    except Exception as e:
        logger.error(f"[Template CSS] Failed to load: {str(e)}")
        return ""


def inject_css_into_html(html: str, css: str) -> str:
    """Inject CSS into HTML document"""
    if not css:
        logger.warning("[CSS Injection] No CSS provided, returning original HTML")
        return html
    
    try:
        # Check if HTML already has style tag
        if '<style>' in html and '</style>' in html:
            # Replace existing style content
            soup = BeautifulSoup(html, 'html.parser')
            style_tag = soup.find('style')
            if style_tag:
                style_tag.string = css
                result = str(soup)
            else:
                result = html.replace('</head>', f'<style>{css}</style></head>')
        else:
            # Inject new style tag
            if '</head>' in html:
                result = html.replace('</head>', f'<style>{css}</style></head>')
            else:
                result = f'<style>{css}</style>{html}'
        
        logger.info(f"[CSS Injection] ✓ Injected {len(css)} characters")
        return result
        
    except Exception as e:
        logger.error(f"[CSS Injection] Failed: {str(e)}")
        return html


def load_wrapper_template(page_size: str = "US-Letter") -> str:
    """Load DocRaptor wrapper template"""
    try:
        page_size_folder = page_size.lower().replace("-", "")
        wrapper_path = Path(f"templates/docraptor/{page_size_folder}/wrapper.html")
        
        if not wrapper_path.exists():
            logger.warning(f"[Wrapper] File not found: {wrapper_path}")
            return ""
        
        with open(wrapper_path, 'r', encoding='utf-8') as f:
            wrapper = f.read()
        
        logger.info(f"[Wrapper] ✓ Loaded from {wrapper_path}")
        return wrapper
        
    except Exception as e:
        logger.error(f"[Wrapper] Failed to load: {str(e)}")
        return ""


# ============================================================================
# DocRaptor Client
# ============================================================================

def get_docraptor_client():
    """Initialize DocRaptor API client"""
    api_key = os.getenv('DOCRAPTOR_API_KEY')
    if not api_key:
        raise ValueError("DOCRAPTOR_API_KEY environment variable not set")
    
    doc_api = docraptor.DocApi()
    doc_api.api_client.configuration.username = api_key
    
    logger.info("✓ DocRaptor client initialized")
    return doc_api


# ============================================================================
# Main PDF Generation Endpoint
# ============================================================================

@app.post("/api/v1/generate-pdf")
async def generate_pdf(request: GeneratePDFRequest):
    """
    Generate PDF from HTML with template styling and metadata
    
    - Extracts metadata from HTML and request
    - Generates table of contents
    - Injects CSS styling
    - Populates wrapper template with metadata
    - Generates PDF using DocRaptor
    """
    try:
        logger.info(f"[PDF Generation] Starting - Template: {request.templateId}")
        
        # ====================================================================
        # STEP 1: Load Template Assets
        # ====================================================================
        page_size = request.options.pageSize if request.options else "US-Letter"
        
        # Load CSS
        css = load_template_css(request.templateId, page_size)
        if not css:
            logger.warning("[PDF Generation] No CSS loaded, proceeding without styling")
        
        # Load wrapper
        wrapper_html = load_wrapper_template(page_size)
        if not wrapper_html:
            logger.warning("[PDF Generation] No wrapper loaded, using direct HTML")
            wrapper_html = "{{PROPOSAL_CONTENT}}"  # Minimal wrapper
        
        # ====================================================================
        # STEP 2: Extract Metadata
        # ====================================================================
        proposal_data = {}
        if request.metadata:
            proposal_data = {
                'title': request.metadata.get('title'),
                'client_name': request.metadata.get('preparedFor'),
                'rfp_title': request.metadata.get('rfpTitle'),
            }
        
        metadata = extract_metadata_from_html(request.html, proposal_data)
        logger.info(f"[Metadata] Extracted: {metadata}")
        
        # ====================================================================
        # STEP 3: Extract/Generate Table of Contents
        # ====================================================================
        toc_html = extract_toc_from_html(request.html)
        logger.info(f"[TOC] Generated {len(toc_html)} characters")
        
        # ====================================================================
        # STEP 4: Get Company Info (from env vars or request)
        # ====================================================================
        company_name = os.getenv('COMPANY_NAME', '')
        company_website = os.getenv('COMPANY_WEBSITE', '')
        company_email = os.getenv('COMPANY_EMAIL', '')
        company_logo_url = os.getenv('COMPANY_LOGO_URL', '')
        
        # Override with request metadata if provided
        if request.metadata:
            company_name = request.metadata.get('companyName', company_name)
            company_website = request.metadata.get('companyWebsite', company_website)
            company_email = request.metadata.get('companyEmail', company_email)
            company_logo_url = request.metadata.get('logoUrl', company_logo_url)
        
        # ====================================================================
        # STEP 5: Inject CSS into Proposal Content
        # ====================================================================
        styled_html = inject_css_into_html(request.html, css)
        
        # ====================================================================
        # STEP 6: Populate Wrapper Template
        # ====================================================================
        wrapper_html = wrapper_html.replace('{{PROPOSAL_TITLE}}', metadata['title'])
        wrapper_html = wrapper_html.replace('{{PROPOSAL_DATE}}', metadata['date'])
        wrapper_html = wrapper_html.replace('{{PREPARED_FOR}}', metadata['prepared_for'])
        wrapper_html = wrapper_html.replace('{{COMPANY_NAME}}', company_name)
        wrapper_html = wrapper_html.replace('{{COMPANY_WEBSITE}}', company_website)
        wrapper_html = wrapper_html.replace('{{COMPANY_EMAIL}}', company_email)
        wrapper_html = wrapper_html.replace('{{LOGO_URL}}', company_logo_url)
        wrapper_html = wrapper_html.replace('{{TABLE_OF_CONTENTS}}', toc_html)
        wrapper_html = wrapper_html.replace('{{PROPOSAL_CONTENT}}', styled_html)
        
        logger.info("[Wrapper] ✓ All placeholders replaced")
        
        # ====================================================================
        # STEP 7: Generate PDF with DocRaptor
        # ====================================================================
        doc_api = get_docraptor_client()
        
        test_mode = request.options.test if request.options else False
        logger.info(f"[DocRaptor] Calling API (test mode: {test_mode})")
        
        pdf_response = doc_api.create_doc({
            "document_content": wrapper_html,
            "name": f"{metadata['title']}.pdf",
            "document_type": "pdf",
            "test": test_mode,
            "prince_options": {
                "media": "print",
                "profile": "PDF/A-1b",
            }
        })
        
        logger.info(f"[PDF Generation] ✓ Complete - {len(pdf_response)} bytes")
        
        # ====================================================================
        # STEP 8: Return PDF
        # ====================================================================
        return Response(
            content=pdf_response,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{metadata["title"]}.pdf"'
            }
        )
        
    except docraptor.rest.ApiException as e:
        logger.error(f"[DocRaptor] API Error: {str(e)}")
        error_detail = e.body if hasattr(e, 'body') else str(e)
        raise HTTPException(status_code=502, detail=f"DocRaptor error: {error_detail}")
        
    except Exception as e:
        logger.error(f"[PDF Generation] ✗ Failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")


# ============================================================================
# PDF Generation with Appendices (Merged)
# ============================================================================

@app.post("/api/v1/generate-pdf-with-appendices")
async def generate_pdf_with_appendices(request: GeneratePDFRequest):
    """
    Generate PDF with appendices merged
    
    - Generates main proposal PDF
    - Fetches PDF attachments from Supabase
    - Merges attachments as appendices
    - Returns complete merged PDF
    """
    try:
        logger.info("[PDF + Appendices] Starting generation")
        
        # Check if Supabase is available
        if not supabase:
            raise HTTPException(
                status_code=503,
                detail="PDF merging unavailable - Supabase not configured"
            )
        
        # Check if user wants appendices
        include_appendices = False
        if request.options:
            include_appendices = request.options.includeAppendices
        
        # ====================================================================
        # STEP 1: Generate Main Proposal PDF (same as generate_pdf)
        # ====================================================================
        # We'll reuse the same logic, but extract it to a helper function
        # For now, call the generate_pdf endpoint internally
        
        # Generate main PDF using the same logic
        page_size = request.options.pageSize if request.options else "US-Letter"
        css = load_template_css(request.templateId, page_size)
        wrapper_html = load_wrapper_template(page_size)
        
        proposal_data = {}
        if request.metadata:
            proposal_data = {
                'title': request.metadata.get('title'),
                'client_name': request.metadata.get('preparedFor'),
                'rfp_title': request.metadata.get('rfpTitle'),
            }
        
        metadata = extract_metadata_from_html(request.html, proposal_data)
        toc_html = extract_toc_from_html(request.html)
        
        # Get company info
        company_name = os.getenv('COMPANY_NAME', request.metadata.get('companyName', '') if request.metadata else '')
        company_website = os.getenv('COMPANY_WEBSITE', request.metadata.get('companyWebsite', '') if request.metadata else '')
        company_email = os.getenv('COMPANY_EMAIL', request.metadata.get('companyEmail', '') if request.metadata else '')
        company_logo_url = os.getenv('COMPANY_LOGO_URL', request.metadata.get('logoUrl', '') if request.metadata else '')
        
        styled_html = inject_css_into_html(request.html, css)
        
        # Populate wrapper
        wrapper_html = wrapper_html.replace('{{PROPOSAL_TITLE}}', metadata['title'])
        wrapper_html = wrapper_html.replace('{{PROPOSAL_DATE}}', metadata['date'])
        wrapper_html = wrapper_html.replace('{{PREPARED_FOR}}', metadata['prepared_for'])
        wrapper_html = wrapper_html.replace('{{COMPANY_NAME}}', company_name)
        wrapper_html = wrapper_html.replace('{{COMPANY_WEBSITE}}', company_website)
        wrapper_html = wrapper_html.replace('{{COMPANY_EMAIL}}', company_email)
        wrapper_html = wrapper_html.replace('{{LOGO_URL}}', company_logo_url)
        wrapper_html = wrapper_html.replace('{{TABLE_OF_CONTENTS}}', toc_html)
        wrapper_html = wrapper_html.replace('{{PROPOSAL_CONTENT}}', styled_html)
        
        # Generate main PDF
        doc_api = get_docraptor_client()
        test_mode = request.options.test if request.options else False
        
        main_pdf_bytes = doc_api.create_doc({
            "document_content": wrapper_html,
            "name": f"{metadata['title']}.pdf",
            "document_type": "pdf",
            "test": test_mode,
            "prince_options": {
                "media": "print",
                "profile": "PDF/A-1b",
            }
        })
        
        logger.info(f"[Main PDF] ✓ Generated {len(main_pdf_bytes)} bytes")
        
        # If not including appendices, return main PDF
        if not include_appendices:
            logger.info("[PDF + Appendices] Returning main PDF only")
            return Response(
                content=main_pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'attachment; filename="{metadata["title"]}.pdf"'
                }
            )
        
        # ====================================================================
        # STEP 2: Fetch Attachments from Supabase
        # ====================================================================
        proposal_id = request.metadata.get('proposalId') if request.metadata else None
        if not proposal_id:
            logger.warning("[PDF + Appendices] No proposal ID - returning main PDF only")
            return Response(
                content=main_pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'attachment; filename="{metadata["title"]}.pdf"'
                }
            )
        
        logger.info(f"[Attachments] Fetching for proposal: {proposal_id}")
        
        # Query section_attachments table
        result = supabase.table('section_attachments') \
            .select('library_item_id, library_documents(storage_path, title, mime_type, original_filename)') \
            .eq('proposal_id', proposal_id) \
            .execute()
        
        # Filter for PDF attachments only
        pdf_attachments = []
        for item in result.data:
            if not item.get('library_documents'):
                continue
            
            doc = item['library_documents']
            mime_type = doc.get('mime_type', '')
            
            if mime_type == 'application/pdf':
                storage_path = doc.get('storage_path')
                title = doc.get('title') or doc.get('original_filename', 'Attachment')
                
                # Get public URL
                public_url = supabase.storage.from_('rfp-uploads').get_public_url(storage_path)
                
                pdf_attachments.append({
                    'title': title,
                    'url': public_url,
                    'file_type': 'PDF'
                })
        
        logger.info(f"[Attachments] Found {len(pdf_attachments)} PDF attachments")
        
        if not pdf_attachments:
            logger.info("[PDF + Appendices] No PDF attachments - returning main PDF only")
            return Response(
                content=main_pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'attachment; filename="{metadata["title"]}.pdf"'
                }
            )
        
        # ====================================================================
        # STEP 3: Merge PDFs
        # ====================================================================
        logger.info("[PDF Merger] Starting merge process")
        merger = PDFMerger()
        merger.add_main_pdf(main_pdf_bytes)
        
        for attachment in pdf_attachments:
            merger.add_attachment(
                title=attachment['title'],
                pdf_url=attachment['url'],
                file_type=attachment['file_type']
            )
        
        merged_pdf_bytes = merger.merge_all()
        
        logger.info(f"[PDF + Appendices] ✓ Complete - {len(merged_pdf_bytes)} bytes")
        
        # ====================================================================
        # STEP 4: Return Merged PDF
        # ====================================================================
        return Response(
            content=merged_pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{metadata["title"]}_with_appendices.pdf"'
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PDF + Appendices] ✗ Failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"PDF generation with appendices failed: {str(e)}"
        )


# ============================================================================
# Health Check and Diagnostic Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint - health check"""
    return {
        "status": "healthy",
        "service": "GovHub Proposal Backend",
        "version": "2.0.0",
        "features": {
            "pdf_generation": True,
            "pdf_merging": supabase is not None,
            "templates": True,
            "metadata_extraction": True
        }
    }


@app.get("/api/v1/health")
async def health():
    """Detailed health check"""
    
    # Check DocRaptor API key
    docraptor_configured = bool(os.getenv('DOCRAPTOR_API_KEY'))
    
    # Check Supabase
    supabase_configured = bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)
    
    # Check template files
    template_check = {
        "usletter_wrapper": Path("templates/docraptor/usletter/wrapper.html").exists(),
        "usletter_css": Path("templates/docraptor/usletter/style.css").exists(),
        "a4_wrapper": Path("templates/docraptor/a4/wrapper.html").exists(),
        "a4_css": Path("templates/docraptor/a4/style.css").exists(),
    }
    
    return {
        "status": "healthy",
        "checks": {
            "docraptor": docraptor_configured,
            "supabase": supabase_configured,
            "templates": all(template_check.values())
        },
        "template_files": template_check,
        "environment": {
            "company_name": bool(os.getenv('COMPANY_NAME')),
            "company_website": bool(os.getenv('COMPANY_WEBSITE')),
            "company_email": bool(os.getenv('COMPANY_EMAIL')),
        }
    }


# ============================================================================
# Error Handlers
# ============================================================================

@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Handle 404 errors"""
    return Response(
        content='{"error": "Not found"}',
        status_code=404,
        media_type="application/json"
    )


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    """Handle 500 errors"""
    logger.error(f"Internal error: {str(exc)}")
    return Response(
        content='{"error": "Internal server error"}',
        status_code=500,
        media_type="application/json"
    )


# ============================================================================
# Application Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
