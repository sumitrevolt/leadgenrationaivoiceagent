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
  
  // Create 14 leadgen combos with proper model names (configuring with our 42 providers)
  const combos = [
    {
      name: 'leadgen-coding-primary',
      description: 'Priority models for coding tasks',
      strategy: 'priority',
      models: [
        { providerId: 'oc', model: 'oc/laguna-s-2.1-free', weight: 1 },
        { providerId: 'oc', model: 'oc/nemotron-3.5-lightning-free', weight: 1 },
        { providerId: 'groq', model: 'groq/llama-3.3-70b', weight: 1 },
        { providerId: 'openrouter', model: 'openrouter/nvidia/nemotron-3.5-lightning:free', weight: 1 },
        { providerId: 'huggingface', model: 'huggingface/deepseek-ai/DeepSeek-V4-Flash', weight: 1 }
      ]
    },
    {
      name: 'leadgen-coding-fast',
      description: 'Fast models for quick responses',
      strategy: 'priority',
      models: [
        { providerId: 'groq', model: 'groq/llama-3.3-70b', weight: 1 },
        { providerId: 'openrouter', model: 'openrouter/nvidia/nemotron-3.5-lightning:free', weight: 1 },
        { providerId: 'huggingface', model: 'huggingface/Qwen/Qwen3.8-2.4T-A95B', weight: 1 },
        { providerId: 'nvidia', model: 'nvidia/nvidia/nemotron-3-super-120b-a12b', weight: 1 },
        { providerId: 'cohere', model: 'cohere/command-r-plus', weight: 1 }
      ]
    },
    {
      name: 'leadgen-agent-ops',
      description: 'AI agent operations models',
      strategy: 'priority',
      models: [
        { providerId: 'zhipu', model: 'zhipu/glm-5.2', weight: 1 },
        { providerId: 'alibaba', model: 'alibaba/qwen3.7-max', weight: 1 },
        { providerId: 'openrouter', model: 'openrouter/nvidia/nemotron-3.5-lightning:free', weight: 1 },
        { providerId: 'groq', model: 'groq/llama-3.3-70b', weight: 1 },
        { providerId: 'huggingface', model: 'huggingface/cohere/command-r-plus', weight: 1 }
      ]
    },
    {
      name: 'leadgen-governor-review',
      description: 'Governor review and compliance models',
      strategy: 'priority',
      models: [
        { providerId: 'volcengine', model: 'volcengine/doubao-seed-2.0-pro', weight: 1 },
        { providerId: 'kunlun', model: 'kunlun/longcat-2.0', weight: 1 },
        { providerId: 'baidu', model: 'baidu/ernie-5.1', weight: 1 },
        { providerId: 'tencent', model: 'tencent/hunyuan-hy3', weight: 1 },
        { providerId: 'sensetime', model: 'sensetime/sensenova-6.7-flash', weight: 1 }
      ]
    },
    {
      name: 'leadgen-repo-analysis',
      description: 'Code repository analysis models',
      strategy: 'priority',
      models: [
        { providerId: 'zhipu', model: 'zhipu/glm-5.2', weight: 1 },
        { providerId: 'alibaba', model: 'alibaba/qwen3.7-max', weight: 1 },
        { providerId: 'baidu', model: 'baidu/ernie-5.1', weight: 1 },
        { providerId: 'tencent', model: 'tencent/hunyuan-hy3', weight: 1 },
        { providerId: 'huggingface', model: 'huggingface/Qwen/Qwen3.8-2.4T-A95B', weight: 1 }
      ]
    },
    {
      name: 'leadgen-test-generation',
      description: 'Test case generation models',
      strategy: 'priority',
      models: [
        { providerId: 'deepseek', model: 'deepseek/deepseek-v4-flash', weight: 1 },
        { providerId: 'alibaba', model: 'alibaba/qwen3.7-max', weight: 1 },
        { providerId: 'volcengine', model: 'volcengine/doubao-seed-2.0-pro', weight: 1 },
        { providerId: 'nvidia', model: 'nvidia/nvidia/nemotron-3-super-120b-a12b', weight: 1 },
        { providerId: 'groq', model: 'groq/llama-3.3-70b', weight: 1 }
      ]
    },
    {
      name: 'leadgen-prospect-enrich',
      description: 'Prospect enrichment and research models',
      strategy: 'priority',
      models: [
        { providerId: 'iflytek', model: 'iflytek/spark-x2', weight: 1 },
        { providerId: 'tencent', model: 'tencent/hunyuan-hy3', weight: 1 },
        { providerId: 'telecom', model: 'telecom/telechat3', weight: 1 },
        { providerId: 'mobile', model: 'mobile/moma-300b', weight: 1 },
        { providerId: 'huggingface', model: 'huggingface/moonshotai/Kimi-K3', weight: 1 }
      ]
    },
    {
      name: 'leadgen-outreach-email',
      description: 'Email outreach and marketing models',
      strategy: 'priority',
      models: [
        { providerId: 'volcengine', model: 'volcengine/doubao-seed-2.0-pro', weight: 1 },
        { providerId: 'kunlun', model: 'kunlun/longcat-2.0', weight: 1 },
        { providerId: '01ai', model: '01ai/yi-lightning', weight: 1 },
        { providerId: 'nvidia', model: 'nvidia/nvidia/nemotron-3-super-120b-a12b', weight: 1 },
        { providerId: 'google', model: 'google/gemini-3.5-flash', weight: 1 }
      ]
    },
    {
      name: 'leadgen-marketing-content',
      description: 'Marketing content generation models',
      strategy: 'priority',
      models: [
        { providerId: 'alibaba', model: 'alibaba/qwen3.7-max', weight: 1 },
        { providerId: 'zhipu', model: 'zhipu/glm-5.2', weight: 1 },
        { providerId: 'volcengine', model: 'volcengine/doubao-seed-2.0-pro', weight: 1 },
        { providerId: 'groq', model: 'groq/llama-3.3-70b', weight: 1 },
        { providerId: 'cohere', model: 'cohere/command-r-plus', weight: 1 }
      ]
    },
    {
      name: 'leadgen-seo-keyword',
      description: 'SEO keyword research models',
      strategy: 'priority',
      models: [
        { providerId: 'tencent', model: 'tencent/hunyuan-hy3', weight: 1 },
        { providerId: 'telecom', model: 'telecom/telechat3', weight: 1 },
        { providerId: 'mobile', model: 'mobile/moma-300b', weight: 1 },
        { providerId: 'sensetime', model: 'sensetime/sensenova-6.7-flash', weight: 1 },
        { providerId: 'huggingface', model: 'huggingface/deepseek-ai/DeepSeek-V4-Flash', weight: 1 }
      ]
    },
    {
      name: 'leadgen-swara-live',
      description: 'Swara Live voice agent models',
      strategy: 'priority',
      models: [
        { providerId: 'deepseek', model: 'deepseek/deepseek-v4-flash', weight: 1 },
        { providerId: 'iflytek', model: 'iflytek/spark-x2', weight: 1 },
        { providerId: 'tencent', model: 'tencent/hunyuan-hy3', weight: 1 },
        { providerId: 'volcengine', model: 'volcengine/doubao-seed-2.0-pro', weight: 1 },
        { providerId: 'groq', model: 'groq/llama-3.3-70b', weight: 1 }
      ]
    },
    {
      name: 'leadgen-free-first',
      description: 'Round-robin free tier models (auto-rotating)',
      strategy: 'round-robin',
      models: [
        { providerId: 'oc', model: 'oc/laguna-s-2.1-free', weight: 1 },
        { providerId: 'oc', model: 'oc/nemotron-3.5-lightning-free', weight: 1 },
        { providerId: 'groq', model: 'groq/llama-3.3-70b', weight: 1 },
        { providerId: 'openrouter', model: 'openrouter/deepseek/deepseek-v4-flash-0731', weight: 1 },
        { providerId: 'huggingface', model: 'huggingface/deepseek-ai/DeepSeek-V4-Flash', weight: 1 }
      ]
    }
  ];
  
  console.log('Creating 14 combos with provider models...\n');
  
  for (const combo of combos) {
    console.log(`Creating: ${combo.name}`);
    try {
      const r = await postJSON('/api/combos', {
        name: combo.name,
        description: combo.description,
        strategy: combo.strategy,
        models: combo.models
      }, apiKey);
      console.log('  Status:', r.status);
      if (r.status === 200 || r.status === 201) {
        console.log('  ✅ Success:', r.data.substring(0, 200));
      } else {
        console.log('  ❌ Error:', r.data.substring(0, 200));
      }
    } catch(e) {
      console.log('  ❌ Exception:', e.message.substring(0, 200));
    }
    // Small delay to avoid rate limiting
    await new Promise(r => setTimeout(r, 500));
  }
  
  console.log('\nDone! Created', combos.length, 'combos.');
}

main();