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
  const apiKey = apiKeyMatch ? apiKeyMatch[1].trim() : 'sk-e9f8e4d8c3b2a1f6e9d7c4b3a2f1e0d9c8b7a6f5e4d3c2b1a0';
  
  // Get all combos
  console.log('=== ALL COMBOS ===');
  const r1 = await getJSON('/api/v1/combos', apiKey);
  if (r1.status === 200) {
    const data = JSON.parse(r1.data);
    const combos = data.data || [];
    console.log('Total:', combos.length);
    
    // Categorize
    const leadgenComos = combos.filter(c => c.name.startsWith('leadgen'));
    const hermesCombos = combos.filter(c => c.name.startsWith('hermes'));
    const otherCombos = combos.filter(c => !c.name.startsWith('leadgen') && !c.name.startsWith('hermes'));
    
    console.log('\n--- LEADGEN COMBOS (' + leadgenComos.length + ') ---');
    leadgenComos.forEach(c => {
      console.log('  ' + c.name + ' | strategy: ' + c.strategy + ' | models: ' + c.models.length);
    });
    
    console.log('\n--- HERMES COMBOS (' + hermesCombos.length + ') ---');
    hermesCombos.forEach(c => {
      console.log('  ' + c.name + ' | strategy: ' + c.strategy + ' | models: ' + c.models.length);
    });
    
    console.log('\n--- OTHER COMBOS (' + otherCombos.length + ') ---');
    otherCombos.forEach(c => {
      console.log('  ' + c.name + ' | strategy: ' + c.strategy + ' | models: ' + c.models.length);
    });
  }
  
  // Get settings
  console.log('\n=== SETTINGS ===');
  const r2 = await getJSON('/api/settings', apiKey);
  if (r2.status === 200) {
    const s = JSON.parse(r2.data);
    console.log('requireLogin:', s.requireLogin);
    console.log('oidcEnabled:', s.oidcEnabled);
    console.log('mcpEnabled:', s.mcpEnabled);
    console.log('cloudEnabled:', s.cloudEnabled);
    console.log('comboStrategy:', s.comboStrategy);
    console.log('providerStrategies:', JSON.stringify(s.providerStrategies));
  }
}

main();