import express from 'express';
import cors from 'cors';
import DocRaptor from 'docraptor';

const app = express();
const PORT = process.env.PORT || 4000;

app.use(cors());
app.use(express.json({ limit: '50mb' }));

const docraptor = new DocRaptor.DocApi();
docraptor.username = process.env.DOCRAPTOR_API_KEY || '9s7j-aM2KHfmgeo1779a';

app.get('/health', (req, res) => {
  res.json({ status: 'ok' });
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
    const { content, template_id } = req.body;
    
    const html = `
      <!DOCTYPE html>
      <html>
        <head>
          <style>
            body { font-family: Arial; margin: 2in; }
            h1 { color: #2563eb; font-size: 28pt; }
            p { font-size: 12pt; line-height: 1.6; }
          </style>
        </head>
        <body>
          <h1>${content.metadata.title}</h1>
          <p>Client: ${content.metadata.client_name}</p>
        </body>
      </html>
    `;

    const doc = {
      test: true,
      document_type: 'pdf',
      document_content: html
    };

    const pdfBuffer = await docraptor.createDoc(doc);
    
    res.setHeader('Content-Type', 'application/pdf');
    res.setHeader('Content-Disposition', 'attachment; filename=proposal.pdf');
    res.send(Buffer.from(pdfBuffer));

  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
