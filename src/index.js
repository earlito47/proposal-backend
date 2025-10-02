const express = require('express');
const cors = require('cors');
const axios = require('axios');
const { GovHubHTMLExtractor } = require('./html-extractor');
const { DocRaptorMapper } = require('./docraptor-mapper');

const app = express();
const PORT = process.env.PORT || 4000;

app.use(cors());
app.use(express.json({ limit: '50mb' }));

app.get('/health', (req, res) => {
  res.json({ status: 'ok' });
});

app.post('/api/v1/apply-template', async (req, res) => {
  try {
    const { proposal_id, template_id } = req.body;
    
    console.log('Fetching HTML from GovHub for proposal:', proposal_id);
    
    // Get HTML from GovHub
    const govhubResponse = await axios.post(
      'https://iqekrwearenblsmhvdjn.supabase.co/functions/v1/generate-proposal-html',
      { proposalId: proposal_id },
      {
        headers: {
          'Content-Type': 'application/json',
          'apikey': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlxZWtyd2VhcmVuYmxzbWh2ZGpuIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTczNTA0NDUsImV4cCI6MjA3MjkyNjQ0NX0.khodqjjwJNovP4cd2fRK3Mdi6VG-HNp0JzzDzWSY_2Q'
        }
      }
    );
    
    const govhubHTML = govhubResponse.data.html;
    console.log('Received HTML from GovHub');
    
    // Extract content
    const extractor = new GovHubHTMLExtractor(govhubHTML);
    const extracted = extractor.extract();
    console.log('Extracted data:', JSON.stringify(extracted, null, 2));
    
    // Map to DocRaptor template
    const mapper = new DocRaptorMapper();
    const styledHTML = mapper.map(extracted);
    console.log('Mapped to DocRaptor template');
    
    // Generate PDF via DocRaptor
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
          document_content: styledHTML,
          name: `${extracted.title}.pdf`
        }
      }
    });
    
    console.log('PDF generated successfully');
    
    res.setHeader('Content-Type', 'application/pdf');
    res.setHeader('Content-Disposition', `attachment; filename="${extracted.title}.pdf"`);
    res.send(Buffer.from(pdfResponse.data));
    
  } catch (error) {
    console.error('Error:', error.message);
    if (error.response) {
      console.error('Response data:', error.response.data);
    }
    res.status(500).json({ error: error.message });
  }
});

app.listen(PORT, () => console.log('Server running on port ' + PORT));
