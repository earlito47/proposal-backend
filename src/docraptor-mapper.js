const fs = require('fs');
const path = require('path');

class DocRaptorMapper {
  constructor() {
    const templatePath = path.join(__dirname, '..', 'templates', 'proposal.html');
    const cssPath = path.join(__dirname, '..', 'templates', 'style.USLetter.css');
    
    this.template = fs.readFileSync(templatePath, 'utf8');
    this.css = fs.readFileSync(cssPath, 'utf8');
  }

  map(extractedData) {
    let html = this.template;
    
    html = html.replace('Client Name', extractedData.client);
    html = html.replace('04.20.21', extractedData.date);
    
    const chaptersHTML = extractedData.sections.map(s => this.buildChapter(s)).join('\n');
    const insertPoint = html.indexOf('</div>', html.indexOf('coverPage')) + 6;
    html = html.slice(0, insertPoint) + '\n' + chaptersHTML + html.slice(insertPoint);
    
    return `<html><head><style>${this.css}</style></head><body>${html}</body></html>`;
  }

  buildChapter(section) {
    let chapterHTML = `<div class="chapter"><h1>${section.title}</h1>`;
    
    section.content.text.forEach(p => {
      chapterHTML += `<p>${p}</p>`;
    });
    
    section.content.tables.forEach(table => {
      chapterHTML += '<table class="budget"><thead><tr>';
      table.headers.forEach(h => chapterHTML += `<th>${h}</th>`);
      chapterHTML += '</tr></thead><tbody>';
      table.rows.forEach(row => {
        chapterHTML += '<tr>';
        row.forEach(cell => chapterHTML += `<td>${cell}</td>`);
        chapterHTML += '</tr>';
      });
      chapterHTML += '</tbody></table>';
    });
    
    chapterHTML += '</div>';
    return chapterHTML;
  }
}

module.exports = { DocRaptorMapper };
