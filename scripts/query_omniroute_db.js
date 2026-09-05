const sqlite3 = require('sqlite3').verbose();
const db = new sqlite3.Database('C:\\Users\\Ratanshila\\.omniroute\\storage.sqlite');

db.serialize(() => {
  // Get all tables
  db.all("SELECT name FROM sqlite_master WHERE type='table'", (err, tables) => {
    console.log('=== TABLES ===');
    tables.forEach(t => console.log('  ' + t.name));
    
    // Check providers
    db.all("SELECT id, name, type, config FROM providers", (err, providers) => {
      console.log('\n=== PROVIDERS ===');
      providers.forEach(p => {
        console.log('  ID: ' + p.id + ', Name: ' + p.name + ', Type: ' + p.type);
        if (p.config) console.log('    Config: ' + p.config.substring(0, 200));
      });
      
      // Check combos
      db.all("SELECT id, name, models, strategy FROM combos", (err, combos) => {
        console.log('\n=== COMBOS ===');
        combos.forEach(c => {
          console.log('  ID: ' + c.id + ', Name: ' + c.name + ', Strategy: ' + c.strategy);
          if (c.models) {
            const models = JSON.parse(c.models);
            console.log('    Models (' + models.length + '): ' + models.slice(0,5).map(m => m.model).join(', ') + '...');
          }
        });
        
        // Check connections
        db.all("SELECT id, providerId, name, status FROM connections", (err, conns) => {
          console.log('\n=== CONNECTIONS ===');
          conns.forEach(c => {
            console.log('  ID: ' + c.id + ', Provider: ' + c.providerId + ', Name: ' + c.name + ', Status: ' + c.status);
          });
          
          db.close();
        });
      });
    });
  });
});