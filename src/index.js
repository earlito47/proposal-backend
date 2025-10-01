const express = require('express');
const cors = require('cors');
const DocRaptor = require('docraptor');

const app = express();
const PORT = process.env.PORT || 4000;

app.use(cors());
app.use(express.json({ limit: '50mb' }));

const docraptor = new DocRaptor.DocApi();
docraptor.apiClient.authentications['basicAuth'].username = process.env.DOCRAPTOR_API_KEY || '9s7j-aM2KHfmgeo1779a';

app.get('/health', (req, res) => {
  res.json({ status: 'ok', message: 'Server is running' });
});

app.get('/api/v1/templates', (req, res) => {
  res.json({
    templates: [
      { template_id: 'modern-corporate', name: 'Modern Corporate' },
      { template_id: 'government-formal', name: 'Government Formal' }
    ]
  });
});

app.post('/api/v1/apply-template', async (req, res) => {
  try {
    const { content } = req.body;
    
    const html = '<html><head><style>body { font-family: Arial; margin: 2in; } h1 { color: #2563eb; font-size: 28pt; } p { font-size: 12pt; }</style></head><body><h1>' + (content.metadata.title || 'Proposal') + '</h1><p>Client: ' + (content.metadata.client_name || 'N/A') + '</p></body></html>';

    const result = await docraptor.createDoc({
      doc: {
        test: true,
        document_type: 'pdf',
        document_content: html,
        name: 'proposal.pdf'
      }
    });

    res.setHeader('Content-Type', 'application/pdf');
    res.setHeader('Content-Disposition', 'attachment; filename=proposal.pdf');
    res.send(result);

  } catch (error) {
    console.error('Error:', error);
    res.status(500).json({ error: error.message });
  }
});

app.listen(PORT, () => {
  console.log('Server running on port ' + PORT);
});
