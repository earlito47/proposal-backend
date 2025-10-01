const express = require('express');
const cors = require('cors');

const app = express();
const PORT = process.env.PORT || 4000;

app.use(cors());
app.use(express.json());

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

app.post('/api/v1/apply-template', (req, res) => {
  res.json({ 
    message: 'Template endpoint working',
    received: req.body 
  });
});

app.listen(PORT, () => {
  console.log('Server running on port ' + PORT);
});
