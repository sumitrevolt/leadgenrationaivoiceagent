const http = require('http');
const fs = require('fs');

async function getJSON(url, auth = '') {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: '127.0.0.1',
      port: 20128,
      path: url,
      method: 'GET',
      headers: auth ? { 'Authorization': auth } : {}
    };
    
    http.get(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve({ status: res.statusCode, data }));
    }).on('error', (e) => reject(e));
  });
}

async function main() {
  const envContent = fs.readFileSync('C:\\Users\\Ratanshila\\AppData\\Local\\hermes\\.env.omniroute', 'utf8');
  const apiKeyMatch = envContent.match(/OMNIROUTE_API_KEY=(.+)/);
  const apiKey = apiKeyMatch ? apiKeyMatch[1].trim() : '';
  
  // Test the models endpoint with auth
  console.log('=== Testing OmniRoute API ===\n');
  
  // Check what models we actually have with full model listing
  console.log('GET /api/v1/models:');
  try {
    const r = await getJSON('/api/v1/models', apiKey);
    if (r.status === 200) {
      const data = JSON.parse(r.data);
      const models = data.data || [];
      console.log('Total models:', models.length);
      
      // Group by provider
      const byProvider = {};
      models.forEach(m => {
        const parts = m.id.split(':');
        const provider = parts[0] || 'unknown';
        if (!byProvider[provider]) byProvider[provider] = [];
        byProvider[provider].push(m.id);
      });
      
      console.log('\nModels by provider:');
      Object.keys(byProvider).forEach(p => {
        console.log(`  ${p} (${byProvider[p].length}):`);
        byProvider[p].slice(0, 10).forEach(m => console.log('    -', m));
      });
    } else {
      console.log('Status:', r.status);
    }
  } catch(e) {
    console.log('Error:', e.message);
  }
}

main();