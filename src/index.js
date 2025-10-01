const express = require('express');
const cors = require('cors');
const axios = require('axios');

const app = express();
const PORT = process.env.PORT || 4000;

app.use(cors());
app.use(express.json({ limit: '50mb' }));

app.get('/health', (req, res) => {
  res.json({ status: 'ok', message: 'Backend is running' });
});

app.get('/api/v1/templates', (req, res) => {
  res.json({
    templates: [
      { 
        template_id: 'modern-corporate', 
        name: 'Modern Corporate',
        category: 'corporate'
      },
      { 
        template_id: 'government-formal', 
        name: 'Government Formal',
        category: 'government'
      }
    ]
  });
});

app.post('/api/v1/apply-template', async (req, res) => {
  try {
    const { content } = req.body;
    
    const html = '<html><head><style>body { font-family: Arial; margin: 2in; } h1 { color: #2563eb; font-size: 28pt; } p { font-size: 12pt; }</style></head><body><h1>' + (content.metadata.title || 'Proposal') + '</h1><p>Client: ' + (content.metadata.client_name || 'N/A') + '</p></body></html>';

    const pdfResponse = await axios({
      url: 'https://api.docraptor.com/docs',
      method: 'post',
      responseType: 'arraybuffer',
      headers: { 'Content-Type': 'application/json' },
      data: {
        user_credentials: process.env.DOCRAPTOR_API_KEY || '9s7j-aM2KHfmgeo1779a',
        doc: {
          test: true,
          document_type: 'pdf',
          document_content: html,
          name: 'proposal.pdf'
        }
      }
    });
    
    res.setHeader('Content-Type', 'application/pdf');
    res.setHeader('Content-Disposition', 'attachment; filename=proposal.pdf');
    res.send(Buffer.from(pdfResponse.data));

  } catch (error) {
    console.error('DocRaptor error:', error);
    
    if (error.response && error.response.data) {
      const decoder = new TextDecoder('utf-8');
      const errorMessage = decoder.decode(error.response.data);
      return res.status(500).json({ error: errorMessage });
    }
    
    res.status(500).json({ error: 'PDF generation failed' });
  }
});

app.listen(PORT, () => {
  console.log('Server running on port ' + PORT);
});
