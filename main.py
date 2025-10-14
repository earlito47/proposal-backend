"""
GovHub Proposal Backend - FastAPI Application
Handles PDF/DOCX export with template styling and metadata injection
Updated to use complete inline-CSS templates
"""
import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
import docraptor
from supabase import create_client, Client

# Import our custom modules
from src.metadata_extractor import extract_metadata_from_html, extract_toc_from_html
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
    includeAppendices: bool = False


class GeneratePDFRequest(BaseModel):
    """Request model for PDF generation"""
    html: str
    templateId: str
    options: Optional[PDFOptions] = None
    metadata: Optional[Dict[str, Any]] = None


# ============================================================================
# Template Management
# ============================================================================

def load_complete_template(page_size: str = "US-Letter") -> str:
    """
    Load complete template with inline CSS
    
    Args:
        page_size: "US-Letter" or "A4"
        
    Returns:
        Complete HTML template as string
    """
    try:
        page_size_folder = page_size.lower().replace("-", "")  # "US-Letter" -> "usletter"
        template_path = Path(f"templates/docraptor/{page_size_folder}/complete-template.html")
        
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")
        
        with open(template_path, 'r', encoding='utf-8') as f:
            template_html = f.read()
        
        logger.info(f"[Template] ✓ Loaded complete template from {template_path} ({len(template_html)} chars)")
        return template_html
        
    except Exception as e:
        logger.error(f"[Template] Failed to load: {str(e)}")
        raise


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
    Generate PDF using complete inline-CSS template
    
    - Loads complete template (CSS + HTML together)
    - Extracts metadata from HTML and request
    - Generates table of contents
    - Replaces all placeholders
    - Generates PDF using DocRaptor
    """
    try:
        logger.info(f"[PDF Generation] Starting - Template: {request.templateId}")
        
        # ====================================================================
        # STEP 1: Load Complete Template (CSS + HTML together)
        # ====================================================================
        page_size = request.options.pageSize if request.options else "US-Letter"
        template_html = load_complete_template(page_size)
        
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
        logger.info(f"[Metadata] Extracted: title='{metadata['title']}', client='{metadata['prepared_for']}'")
        
        # ====================================================================
        # STEP 3: Get Company Info
        # ====================================================================
        company_name = os.getenv('COMPANY_NAME', '')
        company_website = os.getenv('COMPANY_WEBSITE', '')
        company_email = os.getenv('COMPANY_EMAIL', '')
        company_phone = os.getenv('COMPANY_PHONE', '')
        company_logo_url = os.getenv('COMPANY_LOGO_URL', '')
        
        # Override with request metadata if provided
        if request.metadata:
            company_name = request.metadata.get('companyName', company_name) or company_name
            company_website = request.metadata.get('companyWebsite', company_website) or company_website
            company_email = request.metadata.get('companyEmail', company_email) or company_email
            company_logo_url = request.metadata.get('logoUrl', company_logo_url) or company_logo_url
        
        # Ensure we have at least default values
        company_name = company_name or 'Your Company'
        company_website = company_website or 'yourcompany.com'
        company_email = company_email or 'contact@yourcompany.com'
        company_phone = company_phone or '555-123-4567'
        
        logger.info(f"[Company] Using: {company_name} | {company_email} | {company_phone}")
        
        # ====================================================================
        # STEP 4: Handle Logo Placeholder
        # ====================================================================
        if company_logo_url:
            # Use logo image
            logo_html = f'''<div class="logo" style="position:relative; width:4cm; height:4cm; border-radius:100%; background-color:white; overflow:hidden; display:flex; align-items:center; justify-content:center;">
    <img src="{company_logo_url}" alt="{company_name}" style="max-width:90%; max-height:90%; object-fit:contain;">
</div>'''
            logger.info(f"[Logo] Using logo image: {company_logo_url}")
        else:
            # Use company name in circle
            logo_html = f'''<div class="logo">
    <span>{company_name}</span>
</div>'''
            logger.info(f"[Logo] Using text logo: {company_name}")
        
        # ====================================================================
        # STEP 5: Generate TOC (Optional)
        # ====================================================================
        toc_html = extract_toc_from_html(request.html)
        
        # Wrap TOC in a chapter container if it exists
        if toc_html and toc_html.strip():
            toc_html = f'<div class="chapter">{toc_html}</div>'
            logger.info(f"[TOC] Generated ({len(toc_html)} chars)")
        else:
            toc_html = ''
            logger.info("[TOC] Skipped (no sections found)")
        
        # ====================================================================
        # STEP 6: Replace All Placeholders
        # ====================================================================
        final_html = template_html
        
        # Cover page placeholders
        final_html = final_html.replace('{{LOGO_PLACEHOLDER}}', logo_html)
        final_html = final_html.replace('{{PROPOSAL_TITLE}}', metadata['title'])
        final_html = final_html.replace('{{PREPARED_FOR}}', metadata['prepared_for'])
        final_html = final_html.replace('{{PROPOSAL_DATE}}', metadata['date'])
        
        # Company info placeholders
        final_html = final_html.replace('{{COMPANY_NAME}}', company_name)
        final_html = final_html.replace('{{COMPANY_WEBSITE}}', company_website)
        final_html = final_html.replace('{{COMPANY_EMAIL}}', company_email)
        final_html = final_html.replace('{{COMPANY_PHONE}}', company_phone)
        
        # Content placeholders
        final_html = final_html.replace('{{TABLE_OF_CONTENTS}}', toc_html)
        final_html = final_html.replace('{{PROPOSAL_CONTENT}}', request.html)
        
        logger.info("[Template] ✓ All placeholders replaced")
        
        # ====================================================================
        # STEP 7: Generate PDF with DocRaptor
        # ====================================================================
        doc_api = get_docraptor_client()
        
        test_mode = request.options.test if request.options else False
        logger.info(f"[DocRaptor] Calling API (test mode: {test_mode})")
        
        pdf_response = doc_api.create_doc({
            "document_content": final_html,
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
        logger.error(f"[PDF Generation] ✗ Failed: {str(e)}", exc_info=True)
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
        # STEP 1: Generate Main Proposal PDF
        # ====================================================================
        page_size = request.options.pageSize if request.options else "US-Letter"
        template_html = load_complete_template(page_size)
        
        # Extract metadata
        proposal_data = {}
        if request.metadata:
            proposal_data = {
                'title': request.metadata.get('title'),
                'client_name': request.metadata.get('preparedFor'),
                'rfp_title': request.metadata.get('rfpTitle'),
            }
        
        metadata = extract_metadata_from_html(request.html, proposal_data)
        
        # Get company info
        company_name = os.getenv('COMPANY_NAME', request.metadata.get('companyName', 'Your Company') if request.metadata else 'Your Company')
        company_website = os.getenv('COMPANY_WEBSITE', request.metadata.get('companyWebsite', 'yourcompany.com') if request.metadata else 'yourcompany.com')
        company_email = os.getenv('COMPANY_EMAIL', request.metadata.get('companyEmail', 'contact@yourcompany.com') if request.metadata else 'contact@yourcompany.com')
        company_phone = os.getenv('COMPANY_PHONE', '555-123-4567')
        company_logo_url = os.getenv('COMPANY_LOGO_URL', request.metadata.get('logoUrl', '') if request.metadata else '')
        
        # Handle logo
        if company_logo_url:
            logo_html = f'<div class="logo" style="position:relative; width:4cm; height:4cm; border-radius:100%; background-color:white; overflow:hidden; display:flex; align-items:center; justify-content:center;"><img src="{company_logo_url}" alt="{company_name}" style="max-width:90%; max-height:90%; object-fit:contain;"></div>'
        else:
            logo_html = f'<div class="logo"><span>{company_name}</span></div>'
        
        # Generate TOC
        toc_html = extract_toc_from_html(request.html)
        if toc_html and toc_html.strip():
            toc_html = f'<div class="chapter">{toc_html}</div>'
        else:
            toc_html = ''
        
        # Replace placeholders
        final_html = template_html
        final_html = final_html.replace('{{LOGO_PLACEHOLDER}}', logo_html)
        final_html = final_html.replace('{{PROPOSAL_TITLE}}', metadata['title'])
        final_html = final_html.replace('{{PREPARED_FOR}}', metadata['prepared_for'])
        final_html = final_html.replace('{{PROPOSAL_DATE}}', metadata['date'])
        final_html = final_html.replace('{{COMPANY_NAME}}', company_name)
        final_html = final_html.replace('{{COMPANY_WEBSITE}}', company_website)
        final_html = final_html.replace('{{COMPANY_EMAIL}}', company_email)
        final_html = final_html.replace('{{COMPANY_PHONE}}', company_phone)
        final_html = final_html.replace('{{TABLE_OF_CONTENTS}}', toc_html)
        final_html = final_html.replace('{{PROPOSAL_CONTENT}}', request.html)
        
        # Generate main PDF
        doc_api = get_docraptor_client()
        test_mode = request.options.test if request.options else False
        
        main_pdf_bytes = doc_api.create_doc({
            "document_content": final_html,
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
        # STEP 2: Fetch Attachments from Supabase (FIXED QUERY)
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
        
        # FIXED: Get section IDs first, then query section_attachments
        sections_result = supabase.table('proposal_sections') \
            .select('id') \
            .eq('proposal_id', proposal_id) \
            .execute()
        
        section_ids = [s['id'] for s in sections_result.data] if sections_result.data else []
        logger.info(f"[Attachments] Found {len(section_ids)} sections")
        
        # Get section attachments
        section_attachments = []
        if section_ids:
            result = supabase.table('section_attachments') \
                .select('library_item_id, library_documents!inner(storage_path, title, file_type, original_filename)') \
                .in_('proposal_section_id', section_ids) \
                .eq('mode', 'attach_only') \
                .execute()
            
            section_attachments = result.data or []
            logger.info(f"[Attachments] Found {len(section_attachments)} section attachments")
        
        # Get global attachments
        global_result = supabase.table('proposal_global_attachments') \
            .select('library_item_id, library_documents!inner(storage_path, title, file_type, original_filename)') \
            .eq('proposal_id', proposal_id) \
            .eq('mode', 'attach_only') \
            .execute()
        
        global_attachments = global_result.data or []
        logger.info(f"[Attachments] Found {len(global_attachments)} global attachments")
        
        # Combine and filter for PDFs only
        all_attachments = section_attachments + global_attachments
        pdf_attachments = []
        
        for item in all_attachments:
            if not item.get('library_documents'):
                continue
            
            doc = item['library_documents']
            file_type = doc.get('file_type', '')
            
            if file_type == 'application/pdf':
                storage_path = doc.get('storage_path')
                if not storage_path:
                    logger.warning(f"[Attachments] No storage_path for document")
                    continue
                
                # Get signed URL (more reliable than public URL)
                try:
                    clean_path = storage_path.lstrip('/')
                    signed_url = supabase.storage.from_('rfp-uploads').create_signed_url(
                        clean_path, 
                        expires_in=3600  # 1 hour
                    )
                    
                    title = doc.get('title') or doc.get('original_filename', 'Attachment')
                    pdf_url = signed_url['signedURL']
                    
                    pdf_attachments.append({
                        'title': title,
                        'url': pdf_url,
                        'file_type': 'PDF'
                    })
                    
                    logger.info(f"[Attachments] ✓ Queued: {title}")
                    
                except Exception as e:
                    logger.error(f"[Attachments] Failed to get URL for {storage_path}: {e}")
                    continue
        
        logger.info(f"[Attachments] Total PDF attachments to merge: {len(pdf_attachments)}")
        
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
        logger.error(f"[PDF + Appendices] ✗ Failed: {str(e)}", exc_info=True)
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
            "templates": "complete_inline_css",
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
        "usletter_template": Path("templates/docraptor/usletter/complete-template.html").exists(),
        "a4_template": Path("templates/docraptor/a4/complete-template.html").exists(),
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
            "company_phone": bool(os.getenv('COMPANY_PHONE')),
            "company_logo_url": bool(os.getenv('COMPANY_LOGO_URL')),
        }
    }


# ============================================================================
# Test Template Endpoint (Development Only)
# ============================================================================

@app.get("/test-template")
async def test_template():
    """Test template with dummy data - useful for debugging"""
    try:
        template_html = load_complete_template("US-Letter")
        
        # Replace with test data
        test_html = template_html.replace('{{PROPOSAL_TITLE}}', 'Test Proposal')
        test_html = test_html.replace('{{PREPARED_FOR}}', 'Acme Corporation')
        test_html = test_html.replace('{{PROPOSAL_DATE}}', '10.14.25')
        test_html = test_html.replace('{{COMPANY_NAME}}', 'Test Company')
        test_html = test_html.replace('{{COMPANY_WEBSITE}}', 'testcompany.com')
        test_html = test_html.replace('{{COMPANY_EMAIL}}', 'info@testcompany.com')
        test_html = test_html.replace('{{COMPANY_PHONE}}', '555-1234')
        test_html = test_html.replace('{{LOGO_PLACEHOLDER}}', '<div class="logo"><span>Test Company</span></div>')
        test_html = test_html.replace('{{TABLE_OF_CONTENTS}}', '')
        test_html = test_html.replace('{{PROPOSAL_CONTENT}}', '<div class="chapter"><h1>Test Section</h1><p>This is a test of the template system.</p></div>')
        
        # Generate PDF
        doc_api = get_docraptor_client()
        
        pdf_response = doc_api.create_doc({
            "document_content": test_html,
            "name": "test.pdf",
            "document_type": "pdf",
            "test": False,  # Production mode to avoid watermark
            "prince_options": {
                "media": "print",
                "profile": "PDF/A-1b",
            }
        })
        
        return Response(
            content=pdf_response,
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="test.pdf"'}
        )
        
    except Exception as e:
        logger.error(f"[Test] Failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Templates Endpoints
# ============================================================================

@app.get("/api/v1/templates")
async def get_templates():
    """
    Return available DocRaptor templates
    """
    templates = [
        {
            "id": "professional-proposal",
            "name": "Professional Proposal",
            "description": "Clean, modern template with blue gradient cover page and professional layout. Includes table of contents and structured sections.",
            "page_size": "US-Letter",
            "preview_url": None,
            "features": [
                "Blue gradient cover page",
                "Automatic table of contents",
                "Professional typography (Montserrat)",
                "Structured section layouts",
                "Page numbers and headers"
            ],
            "use_case": "General business proposals, federal bids, and government contracts",
            "available": True
        },
        {
            "id": "professional-proposal-a4",
            "name": "Professional Proposal (A4)",
            "description": "Same professional template optimized for A4 paper size (international standard).",
            "page_size": "A4",
            "preview_url": None,
            "features": [
                "A4 page size",
                "Blue gradient cover page",
                "Automatic table of contents",
                "Professional typography"
            ],
            "use_case": "International proposals and European contracts",
            "available": True
        }
    ]
    
    logger.info(f"[Templates] Returning {len(templates)} available templates")
    return templates


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
