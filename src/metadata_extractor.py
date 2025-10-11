"""
Metadata extraction utilities for proposal generation
"""
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


def extract_metadata_from_html(html: str, proposal_data: Optional[Dict] = None) -> Dict[str, str]:
    """
    Extract metadata from HTML and merge with proposal data
    
    Args:
        html: HTML content of the proposal
        proposal_data: Optional dict with proposal metadata
        
    Returns:
        Dict containing extracted metadata
    """
    if proposal_data is None:
        proposal_data = {}
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract title from HTML
    title_elem = soup.find('h1', class_='proposal-title') or soup.find('title')
    proposal_title = proposal_data.get('title', 'Proposal')
    if title_elem and title_elem.text.strip():
        proposal_title = title_elem.text.strip()
    
    # Extract date from HTML or use current date
    date_elem = soup.find(class_='proposal-date')
    proposal_date = datetime.now().strftime("%m.%d.%y")
    if date_elem and date_elem.text.strip():
        proposal_date = date_elem.text.strip()
    
    # Extract or use provided client name
    prepared_for = proposal_data.get('client_name', 'Client Name')
    client_elem = soup.find(class_='client-name')
    if client_elem and client_elem.text.strip():
        prepared_for = client_elem.text.strip()
    
    metadata = {
        'title': proposal_title,
        'date': proposal_date,
        'prepared_for': prepared_for,
        'rfp_title': proposal_data.get('rfp_title', '')
    }
    
    logger.info(f"[Metadata Extractor] Extracted metadata: {metadata}")
    return metadata


def extract_toc_from_html(html: str) -> str:
    """
    Extract or generate table of contents from HTML
    
    Args:
        html: HTML content of the proposal
        
    Returns:
        HTML string containing table of contents
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Try to find existing TOC
    toc_elem = soup.find('div', class_='table-of-contents')
    if not toc_elem:
        toc_elem = soup.find(id='toc')
    
    if toc_elem:
        logger.info("[TOC Extractor] Found existing TOC")
        return str(toc_elem)
    
    # Generate TOC from section headings
    logger.info("[TOC Extractor] Generating TOC from headings")
    
    # Look for section titles with specific class
    sections = soup.find_all('h1', class_='section-title')
    
    # Fallback to any h1 or h2 tags
    if not sections:
        sections = soup.find_all(['h1', 'h2'])
    
    if not sections:
        logger.warning("[TOC Extractor] No headings found for TOC generation")
        return ""
    
    # Build TOC HTML
    toc_html = '''
    <div class="table-of-contents">
        <h2 style="color: #1e3a8a; font-size: 24px; margin-bottom: 20px;">Table of Contents</h2>
        <ol style="list-style-position: inside; line-height: 2;">
    '''
    
    for i, section in enumerate(sections, 1):
        section_title = section.get_text().strip()
        section_id = section.get('id', f'section-{i}')
        
        # Add to TOC
        toc_html += f'''
            <li style="margin-bottom: 8px;">
                <a href="#{section_id}" style="color: #2563eb; text-decoration: none;">
                    {section_title}
                </a>
            </li>
        '''
    
    toc_html += '''
        </ol>
    </div>
    '''
    
    logger.info(f"[TOC Extractor] Generated TOC with {len(sections)} sections")
    return toc_html


def generate_appendix_list_html(attachments: list) -> str:
    """
    Generate HTML list of appendices
    
    Args:
        attachments: List of attachment dicts with 'title' and optionally 'file_type'
        
    Returns:
        HTML string listing all appendices
    """
    if not attachments:
        return ""
    
    html = '''
    <div class="appendices-list" style="margin-top: 40px; page-break-before: always;">
        <h2 style="color: #1e3a8a; font-size: 24px; margin-bottom: 20px;">Appendices</h2>
        <p style="margin-bottom: 20px;">The following supporting documents are available separately:</p>
        <ol style="list-style-position: inside; line-height: 2;">
    '''
    
    for i, attachment in enumerate(attachments, 1):
        letter = chr(64 + i)  # A, B, C, ...
        title = attachment.get('title', f'Attachment {i}')
        file_type = attachment.get('file_type', 'PDF')
        
        html += f'''
            <li style="margin-bottom: 12px;">
                <strong>Appendix {letter}:</strong> {title} ({file_type})
            </li>
        '''
    
    html += '''
        </ol>
    </div>
    '''
    
    logger.info(f"[Appendix List] Generated list with {len(attachments)} items")
    return html
