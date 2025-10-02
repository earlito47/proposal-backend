const { JSDOM } = require('jsdom');

class GovHubHTMLExtractor {
  constructor(html) {
    this.dom = new JSDOM(html);
    this.doc = this.dom.window.document;
  }

  extract() {
    return {
      title: this.extractTitle(),
      client: this.extractClient(),
      date: new Date().toLocaleDateString(),
      sections: this.extractSections()
    };
  }

  extractTitle() {
    const h1 = this.doc.querySelector('h1');
    return h1 ? h1.textContent.trim() : 'Untitled Proposal';
  }

  extractClient() {
    const bodyText = this.doc.body.textContent;
    const rfpMatch = bodyText.match(/RFP[:\s]+([^\n]+)/i);
    return rfpMatch ? rfpMatch[1].trim() : 'Client Name';
  }

  extractSections() {
    const sections = [];
    const headers = this.doc.querySelectorAll('h2, h3');
    
    headers.forEach(header => {
      sections.push({
        title: header.textContent.trim(),
        content: this.extractSectionContent(header)
      });
    });
    
    return sections;
  }

  extractSectionContent(header) {
    const content = { text: [], tables: [] };
    let sibling = header.nextElementSibling;
    
    while (sibling && !['H1', 'H2', 'H3'].includes(sibling.tagName)) {
      if (sibling.tagName === 'P') {
        content.text.push(sibling.textContent.trim());
      }
      if (sibling.tagName === 'TABLE') {
        content.tables.push(this.extractTable(sibling));
      }
      sibling = sibling.nextElementSibling;
    }
    
    return content;
  }

  extractTable(tableElement) {
    const headers = [];
    const rows = [];
    
    tableElement.querySelectorAll('th').forEach(th => {
      headers.push(th.textContent.trim());
    });
    
    tableElement.querySelectorAll('tbody tr').forEach(tr => {
      const row = [];
      tr.querySelectorAll('td').forEach(td => {
        row.push(td.textContent.trim());
      });
      rows.push(row);
    });
    
    return { headers, rows };
  }
}

module.exports = { GovHubHTMLExtractor };
