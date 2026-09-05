const http = require('http');
const fs = require('fs');

async function postJSON(url, body, auth = '') {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify(body);
    const options = {
      hostname: '127.0.0.1',
      port: 20128,
      path: url,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': data.length,
        ...(auth ? { 'Authorization': auth } : {})
      }
    };
    
    const req = http.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve({ status: res.statusCode, data }));
    });
    
    req.on('error', (e) => reject(e));
    req.write(data);
    req.end();
  });
}

async function main() {
  const envContent = fs.readFileSync('C:\\Users\\Ratanshila\\AppData\\Local\\hermes\\.env.omniroute', 'utf8');
  const apiKeyMatch = envContent.match(/OMNIROUTE_API_KEY=(.+)/);
  const apiKey = apiKeyMatch ? apiKeyMatch[1].trim() : 'sk-e9f8e4d8c3b2a1f6e9d7c4b3a2f1e0d9c8b7a6f5e4d3c2b1a0';
  
  // Try different create endpoints
  const endpoints = [
    '/api/v1/combos',
    '/api/combos', 
    '/api/providers',
    '/api/providers',
    '/combos',
    '/providers'
  ];
  
  for (const ep of endpoints) {
    console.log(`\n=== POST ${ep} ===`);
    try {
      const r = await postJSON(ep, { name: 'test-combo', strategy: 'priority' }, apiKey);
      console.log('Status:', r.status, '| Data:', r.data.substring(0, 200));
    } catch(e) {
      console.log('Error:', e.message.substring(0, 200));
    }
  }
}

main();