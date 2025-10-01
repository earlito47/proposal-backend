const express = require('express');
const cors = require('cors');
const DocRaptor = require('docraptor');

const app = express();
const PORT = process.env.PORT || 4000;

app.use(cors());
app.use(express.json({ limit: '50mb' }));

// Initialize DocRaptor - simpler approach
const docraptor = new DocRaptor.DocApi();
docraptor.apiClient.authentications['basicAuth'].username = process.env.DOCRAPTOR_API_KEY || '9s7j-aM2KHfmgeo1            body { font-family: Arial; margin: 2in; }
            h1 { color: #2563eb; font-size: 28pt; }
            p { font-size: 12pt; line-height: 1.6; }
          </style>
        </head>
        <body>
          <h1>${content.metadata?.title || 'Proposal'}</h1>
          <p>Client: ${content.metadata?.client_name || 'N/A'}</p>
        </body>
      </html>
    `;

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
