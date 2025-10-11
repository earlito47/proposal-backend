"""
PDF merging utilities for combining proposals with appendices
"""
import pikepdf
from pikepdf import Pdf
import requests
import io
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class PDFMerger:
    """Handles merging of proposal PDFs with attachment appendices"""
    
    def __init__(self):
        self.main_pdf: Optional[Pdf] = None
        self.attachments: List[Dict] = []
        self.merged_pages = 0
        
    def add_main_pdf(self, pdf_bytes: bytes) -> None:
        """
        Load the main proposal PDF
        
        Args:
            pdf_bytes: Raw bytes of the main PDF document
        """
        try:
            self.main_pdf = Pdf.open(io.BytesIO(pdf_bytes))
            page_count = len(self.main_pdf.pages)
            self.merged_pages = page_count
            logger.info(f"[PDF Merger] Main PDF loaded: {page_count} pages")
        except Exception as e:
            logger.error(f"[PDF Merger] Failed to load main PDF: {str(e)}")
            raise
    
    def add_attachment(self, title: str, pdf_url: str, file_type: str = 'PDF') -> None:
        """
        Queue an attachment for merging
        
        Args:
            title: Display title for the attachment
            pdf_url: Public URL to download the PDF
            file_type: File type label (default: 'PDF')
        """
        self.attachments.append({
            'title': title,
            'url': pdf_url,
            'file_type': file_type
        })
        logger.info(f"[PDF Merger] Queued attachment: {title}")
    
    def download_pdf(self, url: str) -> Optional[bytes]:
        """
        Download PDF from URL
        
        Args:
            url: Public URL of the PDF
            
        Returns:
            PDF bytes or None if download fails
        """
        try:
            logger.info(f"[PDF Merger] Downloading: {url}")
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            
            # Verify content type
            content_type = response.headers.get('Content-Type', '')
            if 'pdf' not in content_type.lower():
                logger.warning(f"[PDF Merger] Unexpected content type: {content_type}")
            
            logger.info(f"[PDF Merger] Downloaded {len(response.content)} bytes")
            return response.content
            
        except requests.exceptions.Timeout:
            logger.error(f"[PDF Merger] Download timeout: {url}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"[PDF Merger] Download failed: {url} - {str(e)}")
            return None
        except Exception as e:
            logger.error(f"[PDF Merger] Unexpected error downloading {url}: {str(e)}")
            return None
    
    def create_appendix_divider_page(
        self, 
        letter: str, 
        title: str,
        page_number: int
    ) -> Optional[Pdf]:
        """
        Create a divider page for an appendix
        
        Args:
            letter: Appendix letter (A, B, C, ...)
            title: Appendix title
            page_number: Starting page number for this appendix
            
        Returns:
            Pdf object with single divider page, or None
            
        Note: 
            This is a placeholder. Full implementation would require
            HTML-to-PDF conversion for styled divider pages.
        """
        # TODO: Implement styled divider pages
        # For v1, we'll skip divider pages and just merge the PDFs directly
        return None
    
    def merge_all(self) -> bytes:
        """
        Merge main PDF with all attachments
        
        Returns:
            Merged PDF as bytes
            
        Raises:
            ValueError: If no main PDF is loaded
            Exception: If merge fails
        """
        if not self.main_pdf:
            raise ValueError("[PDF Merger] No main PDF loaded")
        
        try:
            # Create output PDF starting with main content
            output = Pdf.new()
            output.pages.extend(self.main_pdf.pages)
            logger.info(f"[PDF Merger] Added main content: {len(self.main_pdf.pages)} pages")
            
            # Track page numbers and successful merges
            current_page = len(output.pages)
            successful_merges = []
            failed_merges = []
            
            # Add each attachment
            for i, attachment in enumerate(self.attachments):
                appendix_letter = chr(65 + i)  # A, B, C, ...
                
                try:
                    # Download attachment PDF
                    pdf_bytes = self.download_pdf(attachment['url'])
                    if not pdf_bytes:
                        failed_merges.append({
                            'letter': appendix_letter,
                            'title': attachment['title'],
                            'reason': 'Download failed'
                        })
                        logger.warning(f"[PDF Merger] Skipping {attachment['title']} - download failed")
                        continue
                    
                    # Open attachment PDF
                    attach_pdf = Pdf.open(io.BytesIO(pdf_bytes))
                    page_count = len(attach_pdf.pages)
                    
                    # Add attachment pages
                    start_page = current_page + 1
                    output.pages.extend(attach_pdf.pages)
                    current_page += page_count
                    
                    # Track successful merge
                    successful_merges.append({
                        'letter': appendix_letter,
                        'title': attachment['title'],
                        'start_page': start_page,
                        'page_count': page_count
                    })
                    
                    logger.info(
                        f"[PDF Merger] ✓ Appendix {appendix_letter}: {attachment['title']} "
                        f"({page_count} pages, starting at page {start_page})"
                    )
                    
                    # Close attachment to free memory
                    attach_pdf.close()
                    
                except Exception as e:
                    failed_merges.append({
                        'letter': appendix_letter,
                        'title': attachment['title'],
                        'reason': str(e)
                    })
                    logger.error(f"[PDF Merger] Failed to merge {attachment['title']}: {str(e)}")
                    continue
            
            # Add PDF metadata
            with output.open_metadata() as meta:
                meta['dc:title'] = 'Proposal with Appendices'
                meta['dc:creator'] = 'GovHub'
                meta['dc:subject'] = 'Government Proposal'
            
            # Save to bytes
            output_buffer = io.BytesIO()
            output.save(output_buffer)
            output.close()
            
            # Log summary
            total_pages = len(output.pages)
            logger.info(
                f"[PDF Merger] ✓ Merge complete: {total_pages} total pages, "
                f"{len(successful_merges)} appendices merged, "
                f"{len(failed_merges)} failed"
            )
            
            if failed_merges:
                logger.warning(f"[PDF Merger] Failed merges: {failed_merges}")
            
            return output_buffer.getvalue()
            
        except Exception as e:
            logger.error(f"[PDF Merger] Merge failed: {str(e)}")
            raise
        finally:
            # Cleanup
            if self.main_pdf:
                try:
                    self.main_pdf.close()
                except:
                    pass
    
    def get_attachment_count(self) -> int:
        """Get number of queued attachments"""
        return len(self.attachments)
    
    def clear_attachments(self) -> None:
        """Clear all queued attachments"""
        self.attachments.clear()
        logger.info("[PDF Merger] Cleared all attachments")
