const http = require('http');

async function probe(url, auth = '') {
  return new Promise((resolve) => {
    const options = {
      headers: auth ? { 'Authorization': auth } : {}
    };
    http.get(url, options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve({ status: res.statusCode, data, headers: res.headers }));
    }).on('error', (e) => resolve({ error: e.message }));
  });
}

async function main() {
  const fs = require('fs');
  const envContent = fs.readFileSync('C:\\Users\\Ratanshila\\AppData\\Local\\hermes\\.env.omniroute', 'utf8');
  const apiKeyMatch = envContent.match(/OMNIROUTE_API_KEY=(.+)/);
  const apiKey = apiKeyMatch ? apiKeyMatch[1].trim() : 'sk-e9f8e4d8c3b2a1f6e9d7c4b3a2f1e0d9c8b7a6f5e4d3c2b1a0';
  
  console.log('Using API Key:', apiKey.substring(0, 20) + '...');
  
  // Get existing combos
  console.log('\n=== GET /api/v1/combos ===');
  const r1 = await probe('http://127.0.0.1:20128/api/v1/combos', apiKey);
  console.log('Status:', r1.status);
  if (r1.status === 200) {
    const data = JSON.parse(r1.data);
    console.log('Total combos:', data.data.length);
    data.data.forEach(c => {
      console.log('  -', c.name, '| strategy:', c.strategy, '| models:', c.models.length);
    });
  }
  
  // Get all models from v1/models
  console.log('\n=== GET /v1/models ===');
  const r2 = await probe('http://127.0.0.1:20128/v1/models', apiKey);
  console.log('Status:', r2.status);
  if (r2.status === 200) {
    const data = JSON.parse(r2.data);
    console.log('Total models:', data.data.length);
    data.data.forEach(m => {
      console.log('  -', m.id, '(owned_by:', m.owned_by + ')');
    });
  }
  
  // Check /api/combos
  console.log('\n=== GET /api/combos ===');
  const r3 = await probe('http://127.0.0.1:20128/api/combos', apiKey);
  console.log('Status:', r3.status);
  if (r3.status === 200) {
    const data = JSON.parse(r3.data);
    console.log('Total combos:', data.combos.length);
    data.combos.forEach(c => {
      console.log('  -', c.name, '| models:', c.models.length);
    });
  }
  
  // Check /api/settings
  console.log('\n=== GET /api/settings ===');
  const r4 = await probe('http://127.0.0.1:20128/api/settings', apiKey);
  console.log('Status:', r4.status);
  if (r4.status === 200) {
    console.log('Settings:', r4.data.substring(0, 1000));
  }
}

main();