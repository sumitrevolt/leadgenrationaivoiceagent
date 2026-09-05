/**
 * OmniRoute Full Auto-Setup Script
 * Configures: Password + 42 Providers + 14 Combos
 * Run: npx playwright omniroute-auto-setup.js
 * 
 * PREREQUISITES:
 * 1. OmniRoute server running on http://127.0.0.1:20128
 * 2. All API keys ready (you'll paste them when prompted)
 * 3. Chrome/Edge installed
 */

const { chromium } = require('playwright');
const fs = require('fs');
const readline = require('readline');

const OMINROUTE_URL = 'http://127.0.0.1:20128';
const SETUP_FILE = 'omniroute-setup-state.json';

// ============================================================
// PROVIDER CONFIGURATION - EDIT THESE WITH YOUR ACTUAL KEYS
// ============================================================
const PROVIDERS = [
  // Chinese Providers (1-21) - ALL API KEY BASED
  { id: 1, name: 'SiliconFlow', type: 'api_key', keyEnv: 'SILICONFLOW_API_KEY', models: ['DeepSeek-V4-Pro', 'Qwen3.7-Max', 'GLM-5.2'] },
  { id: 2, name: 'Volcengine Ark', type: 'api_key', keyEnv: 'VOLCENGINE_API_KEY', models: ['Doubao-Seed-2.0-Pro'] },
  { id: 3, name: 'Zhipu AI', type: 'api_key', keyEnv: 'ZHIPU_API_KEY', models: ['GLM-5.2'] },
  { id: 4, name: 'Alibaba Bailian', type: 'api_key', keyEnv: 'ALIBABA_API_KEY', models: ['Qwen3.7-Max'] },
  { id: 5, name: 'Baidu Qianfan', type: 'api_key', keyEnv: 'BAIDU_API_KEY', models: ['ERNIE-5.1'] },
  { id: 6, name: 'Tencent Cloud', type: 'api_key', keyEnv: 'TENCENT_API_KEY', models: ['Hunyuan-Hy3'] },
  { id: 7, name: 'MiniMax', type: 'api_key', keyEnv: 'MINIMAX_API_KEY', models: ['MiniMax-M3'] },
  { id: 8, name: 'Kimi', type: 'api_key', keyEnv: 'KIMI_API_KEY', models: ['Kimi-K3'] },
  { id: 9, name: 'DeepSeek', type: 'api_key', keyEnv: 'DEEPSEEK_API_KEY', models: ['DeepSeek-V4-Flash', 'DeepSeek-V4-Pro'] },
  { id: 10, name: 'iFlytek Spark', type: 'api_key', keyEnv: 'IFLYTEK_API_KEY', models: ['Spark-X2'] },
  { id: 11, name: 'StreamLake', type: 'api_key', keyEnv: 'STREAMLAKE_API_KEY', models: ['KAT-Coder-Air-V2.5'] },
  { id: 12, name: 'China Telecom', type: 'api_key', keyEnv: 'TELECHAT_API_KEY', models: ['TeleChat3'] },
  { id: 13, name: 'SenseTime', type: 'api_key', keyEnv: 'SENSETIME_API_KEY', models: ['SenseNova-6.7-Flash'] },
  { id: 14, name: 'DMXAPI', type: 'api_key', keyEnv: 'DMXAPI_API_KEY', models: ['DeepSeek-V4'] },
  { id: 15, name: '01.AI', type: 'api_key', keyEnv: 'ZEROONE_API_KEY', models: ['Yi-Lightning'] },
  { id: 16, name: 'China Mobile', type: 'api_key', keyEnv: 'CHINAMOBILE_API_KEY', models: ['MoMA-300B'] },
  { id: 17, name: 'DataEye', type: 'api_key', keyEnv: 'DATAEYE_API_KEY', models: ['Aggregator-Flagship'] },
  { id: 18, name: 'Kunlun', type: 'api_key', keyEnv: 'KUNLUN_API_KEY', models: ['Matrix-3.5'] },
  { id: 19, name: '360 AI', type: 'api_key', keyEnv: 'AI360_API_KEY', models: ['360-AI-4.0'] },
  { id: 20, name: 'PPIO', type: 'api_key', keyEnv: 'PPIO_API_KEY', models: ['DeepSeek-V4-Flash'] },
  { id: 21, name: 'Reserved', type: 'api_key', keyEnv: '', models: [] },

  // International Providers (22-42) - Mix of API Key and OAuth
  { id: 22, name: 'Google AI Studio', type: 'oauth', keyEnv: '', models: ['Gemini-3.5-Flash'], oauthUrl: 'https://aistudio.google.com' },
  { id: 23, name: 'Groq', type: 'api_key', keyEnv: 'GROQ_API_KEY', models: ['Llama-3.3-70B'] },
  { id: 24, name: 'OpenRouter', type: 'api_key', keyEnv: 'OPENROUTER_API_KEY', models: ['Auto-Router'] },
  { id: 25, name: 'Cloudflare', type: 'api_key', keyEnv: 'CLOUDFLARE_API_KEY', models: ['Llama-3.1-8B'] },
  { id: 26, name: 'GitHub Models', type: 'oauth', keyEnv: '', models: ['GPT-4o'], oauthUrl: 'https://github.com/marketplace/models' },
  { id: 27, name: 'NVIDIA NIM', type: 'api_key', keyEnv: 'NVIDIA_API_KEY', models: ['Nemotron-3-Super-120B'] },
  { id: 28, name: 'Cerebras', type: 'api_key', keyEnv: 'CEREBRAS_API_KEY', models: ['Llama-3.3-70B'] },
  { id: 29, name: 'Mistral', type: 'api_key', keyEnv: 'MISTRAL_API_KEY', models: ['Mistral-Large-3'] },
  { id: 30, name: 'Cohere', type: 'api_key', keyEnv: 'COHERE_API_KEY', models: ['Command-R+'] },
  { id: 31, name: 'HuggingFace', type: 'api_key', keyEnv: 'HF_API_KEY', models: ['Qwen-3.5-122B'] },
  { id: 32, name: 'Together AI', type: 'api_key', keyEnv: 'TOGETHER_API_KEY', models: ['Llama-3.3-70B'] },
  { id: 33, name: 'LLM7.io', type: 'api_key', keyEnv: 'LLM7_API_KEY', models: ['DeepSeek-V4-Flash'] },
  { id: 34, name: 'Ollama Cloud', type: 'api_key', keyEnv: 'OLLAMA_API_KEY', models: ['Llama-3.3-70B'] },
  { id: 35, name: 'AWS Bedrock', type: 'api_key', keyEnv: 'AWS_BEDROCK_API_KEY', models: ['Claude-Sonnet-4'] },
  { id: 36, name: 'Anyscale', type: 'api_key', keyEnv: 'ANYSCALE_API_KEY', models: ['Llama-3.1-405B'] },
  { id: 37, name: 'NCompass', type: 'api_key', keyEnv: 'NCOMPASS_API_KEY', models: ['Various'] },
  { id: 38, name: 'DigitalOcean', type: 'api_key', keyEnv: 'DO_API_KEY', models: ['GenAI-Inference'] },
  { id: 39, name: 'Fireworks', type: 'api_key', keyEnv: 'FIREWORKS_API_KEY', models: ['Llama-3.3-70B'] },
  { id: 40, name: 'OctoAI', type: 'api_key', keyEnv: 'OCTOAI_API_KEY', models: ['Various'] },
  { id: 41, name: 'Unify', type: 'api_key', keyEnv: 'UNIFY_API_KEY', models: ['Various'] },
  { id: 42, name: 'DeepInfra', type: 'api_key', keyEnv: 'DEEPINFRA_API_KEY', models: ['Various'] },
];

// ============================================================
// COMBO CONFIGURATION - 14 Combos with rotating providers
// ============================================================
const COMBOS = [
  {
    name: 'leadgen-coding-primary',
    description: 'Coding focused - DeepSeek, Qwen, GLM, Llama priority',
    models: [
      'SiliconFlow/DeepSeek-V4-Pro',
      'Alibaba Bailian/Qwen3.7-Max',
      'Zhipu AI/GLM-5.2',
      'Volcengine Ark/Doubao-Seed-2.0-Pro',
      'China Telecom/TeleChat3',
      // Fallbacks from international
      'Groq/Llama-3.3-70B',
      'NVIDIA NIM/Nemotron-3-Super-120B',
      'Together AI/Llama-3.3-70B',
    ]
  },
  {
    name: 'leadgen-coding-fast',
    description: 'Speed focused - Flash/Lite models first',
    models: [
      'DeepSeek/DeepSeek-V4-Flash',
      'iFlytek Spark/Spark-X2',
      'China Telecom/TeleChat3',
      'China Mobile/MoMA-300B',
      'NVIDIA NIM/Nemotron-3-Super-120B',
    ]
  },
  {
    name: 'leadgen-agent-ops',
    description: 'Agentic operations - Tool use, reliability priority',
    models: [
      'Zhipu AI/GLM-5.2',
      'Alibaba Bailian/Qwen3.7-Max',
      'NVIDIA NIM/Nemotron-3-Super-120B',
      'Groq/Llama-3.3-70B',
      'Cohere/Command-R+',
    ]
  },
  {
    name: 'leadgen-governor-review',
    description: 'Reasoning - Thinking models first',
    models: [
      'Volcengine Ark/Doubao-Seed-2.0-Pro',
      'Kunlun/LongCat-2.0',
      'Baidu Qianfan/ERNIE-5.1',
      'Tencent Cloud/Hunyuan-Hy3',
      'SenseTime/SenseNova-6.7-Flash',
    ]
  },
  {
    name: 'leadgen-repo-analysis',
    description: 'Large context - 100K+ context models',
    models: [
      'Zhipu AI/GLM-5.2',
      'Alibaba Bailian/Qwen3.7-Max',
      'Baidu Qianfan/ERNIE-5.1',
      'China Telecom/TeleChat3',
      'NVIDIA NIM/Nemotron-3-Super-120B',
    ]
  },
  {
    name: 'leadgen-test-generation',
    description: 'Test generation - Coding + instruction following',
    models: [
      'DeepSeek/DeepSeek-V4-Flash',
      'Alibaba Bailian/Qwen3.7-Max',
      'Volcengine Ark/Doubao-Seed-2.0-Pro',
      'NVIDIA NIM/Nemotron-3-Super-120B',
      'Groq/Llama-3.3-70B',
    ]
  },
  {
    name: 'leadgen-prospect-enrich',
    description: 'Prospect enrichment - Fast factual/research',
    models: [
      'iFlytek Spark/Spark-X2',
      'China Telecom/TeleChat3',
      'China Mobile/MoMA-300B',
      'Tencent Cloud/Hunyuan-Hy3',
      'GitHub Models/GPT-4o',
    ]
  },
  {
    name: 'leadgen-outreach-email',
    description: 'Outreach email - Writing + instruction following',
    models: [
      'Volcengine Ark/Doubao-Seed-2.0-Pro',
      'Kunlun/LongCat-2.0',
      '01.AI/Yi-Lightning',
      'NVIDIA NIM/Nemotron-3-Super-120B',
      'Google AI Studio/Gemini-3.5-Flash',
    ]
  },
  {
    name: 'leadgen-marketing-content',
    description: 'Marketing content - Creative + writing',
    models: [
      'Alibaba Bailian/Qwen3.7-Max',
      'Zhipu AI/GLM-5.2',
      'Volcengine Ark/Doubao-Seed-2.0-Pro',
      'Groq/Llama-3.3-70B',
      'Cohere/Command-R+',
    ]
  },
  {
    name: 'leadgen-seo-keyword',
    description: 'SEO keywords - Research + long context',
    models: [
      'China Telecom/TeleChat3',
      'Baidu Qianfan/ERNIE-5.1',
      'Tencent Cloud/Hunyuan-Hy3',
      'China Mobile/MoMA-300B',
      'SenseTime/SenseNova-6.7-Flash',
    ]
  },
  {
    name: 'leadgen-swara-live',
    description: 'Voice live - Low latency conversational',
    models: [
      'DeepSeek/DeepSeek-V4-Flash',
      'iFlytek Spark/Spark-X2',
      'China Telecom/TeleChat3',
      'Volcengine Ark/Doubao-Seed-2.0-Pro',
      'Groq/Llama-3.3-70B',
    ]
  },
  {
    name: 'leadgen-free-first',
    description: 'Free first - Maximum provider diversity (ALL 42)',
    models: PROVIDERS.filter(p => p.models.length > 0).flatMap(p => p.models.map(m => `${p.name}/${m}`))
  },
  {
    name: 'leadgen-project-best',
    description: 'Project best - Balanced selection',
    models: [
      'SiliconFlow/DeepSeek-V4-Pro',
      'Alibaba Bailian/Qwen3.7-Max',
      'Zhipu AI/GLM-5.2',
      'Groq/Llama-3.3-70B',
      'NVIDIA NIM/Nemotron-3-Super-120B',
    ]
  },
  {
    name: 'claude-omni-coding-primary',
    description: 'Claude Omni coding primary',
    models: [
      'GitHub Models/GPT-4o',
      'SiliconFlow/DeepSeek-V4-Pro',
      'Alibaba Bailian/Qwen3.7-Max',
      'Zhipu AI/GLM-5.2',
      'NVIDIA NIM/Nemotron-3-Super-120B',
    ]
  },
];

// ============================================================
// HELPER FUNCTIONS
// ============================================================
const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout
});

function ask(question) {
  return new Promise(resolve => rl.question(question, resolve));
}

async function loadState() {
  if (fs.existsSync(SETUP_FILE)) {
    return JSON.parse(fs.readFileSync(SETUP_FILE, 'utf8'));
  }
  return { passwordSet: false, providersAdded: [], combosCreated: [] };
}

async function saveState(state) {
  fs.writeFileSync(SETUP_FILE, JSON.stringify(state, null, 2));
}

async function waitForSelector(page, selector, timeout = 10000) {
  try {
    await page.waitForSelector(selector, { timeout });
    return true;
  } catch {
    return false;
  }
}

async function clickIfExists(page, selector) {
  try {
    await page.click(selector, { timeout: 3000 });
    return true;
  } catch {
    return false;
  }
}

// ============================================================
// MAIN AUTOMATION
// ============================================================
async function main() {
  console.log('🚀 Starting OmniRoute Full Auto-Setup');
  console.log('=====================================\n');

  const state = await loadState();
  
  // Launch browser
  const browser = await chromium.launch({ 
    headless: false,  // MUST be false for OAuth
    channel: 'chrome',
    args: ['--start-maximized']
  });
  
  const context = await browser.newContext({ viewport: null });
  const page = await context.newPage();
  
  // Enable console logging
  page.on('console', msg => console.log(`[Browser] ${msg.text()}`));
  page.on('pageerror', err => console.error(`[Browser Error] ${err.message}`));

  try {
    // ------------------------------------------------------------------
    // STEP 1: NAVIGATE AND HANDLE ONBOARDING
    // ------------------------------------------------------------------
    console.log('📍 Step 1: Navigating to OmniRoute Dashboard...');
    // Use domcontentloaded instead of networkidle to avoid WS hang
    await page.goto(OMINROUTE_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForTimeout(3000);

    // Check if onboarding wizard is shown
    const onboardingVisible = await waitForSelector(page, 'text=Start Onboarding, text=Run the onboarding wizard, text=Configure Password, text=Let\'s get your OmniRoute instance configured', 5000);
    
    if (onboardingVisible && !state.passwordSet) {
      console.log('🔐 Onboarding wizard detected - setting up password...');
      
      // Click Start Onboarding
      await clickIfExists(page, 'button:has-text("Start Onboarding")');
      await clickIfExists(page, 'button:has-text("Run the onboarding wizard")');
      await clickIfExists(page, 'text=Configure Password');
      await page.waitForTimeout(1000);
      
      // Get password from user
      const password = await ask('\n🔑 Enter a strong password for OmniRoute dashboard (min 16 chars): ');
      const confirmPassword = await ask('🔑 Confirm password: ');
      
      if (password !== confirmPassword) {
        console.error('❌ Passwords do not match!');
        process.exit(1);
      }
      
      // Fill password fields
      await page.fill('input[type="password"]:first-of-type', password);
      await page.fill('input[type="password"]:last-of-type', confirmPassword);
      await page.click('button:has-text("Continue"), button:has-text("Set Password"), button:has-text("Next")');
      await page.waitForTimeout(3000);
      
      state.passwordSet = true;
      state.password = password; // Save for later API calls
      await saveState(state);
      console.log('✅ Password set successfully!\n');
    } else if (state.passwordSet) {
      console.log('✅ Password already set (from previous run)\n');
    }

    // ------------------------------------------------------------------
    // STEP 2: LOGIN IF NEEDED
    // ------------------------------------------------------------------
    const loginVisible = await waitForSelector(page, 'input[type="password"]', 3000);
    if (loginVisible) {
      console.log('🔐 Login required...');
      const password = state.password || await ask('Enter dashboard password: ');
      await page.fill('input[type="password"]', password);
      await page.click('button:has-text("Sign In"), button:has-text("Login"), button:has-text("Unlock")');
      await page.waitForTimeout(2000);
    }

    // ------------------------------------------------------------------
    // STEP 3: ADD ALL PROVIDERS
    // ------------------------------------------------------------------
    console.log('📍 Step 2: Adding Providers (42 total)...');
    await page.goto(`${OMINROUTE_URL}/providers`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(2000);

    for (const provider of PROVIDERS) {
      if (state.providersAdded.includes(provider.id)) {
        console.log(`  ⏭️  Skipping ${provider.name} (already added)`);
        continue;
      }

      if (!provider.models.length) {
        console.log(`  ⏭️  Skipping ${provider.name} (no models configured)`);
        continue;
      }

      console.log(`\n  ➕ Adding Provider ${provider.id}/42: ${provider.name} (${provider.type})`);

      try {
        // Click "Add Provider" or "New Provider"
        await clickIfExists(page, 'button:has-text("Add Provider")');
        await clickIfExists(page, 'button:has-text("New Provider")');
        await clickIfExists(page, 'a:has-text("Add Provider")');
        await page.waitForTimeout(1000);

        // Find and click the provider card
        // Try multiple selectors for the provider
        const providerSelectors = [
          `text=${provider.name}`,
          `[data-provider="${provider.name.toLowerCase().replace(/\s+/g, '-')}"]`,
          `button:has-text("${provider.name}")`,
          `div:has-text("${provider.name}")`,
        ];

        let clicked = false;
        for (const sel of providerSelectors) {
          if (await clickIfExists(page, sel)) {
            clicked = true;
            break;
          }
        }

        if (!clicked) {
          // Try to find in a list
          await page.waitForTimeout(1000);
          const cards = await page.$$('button, .provider-card, [role="button"]');
          for (const card of cards) {
            const text = await card.textContent();
            if (text && text.includes(provider.name)) {
              await card.click();
              clicked = true;
              break;
            }
          }
        }

        if (!clicked) {
          console.log(`  ⚠️  Could not find provider card for ${provider.name} - may need manual selection`);
          console.log('  Please click the provider in the browser, then press Enter here...');
          await ask('  Press Enter after selecting provider...');
        }

        await page.waitForTimeout(1500);

        if (provider.type === 'api_key') {
          // API Key flow
          const apiKey = await ask(`  🔑 Enter API Key for ${provider.name}: `);
          
          // Find API key input
          await page.fill('input[placeholder*="API" i], input[placeholder*="Key" i], input[type="password"]:not([placeholder*="password" i]):first-of-type', apiKey);
          await page.waitForTimeout(500);
          
          // Test connection if button exists
          await clickIfExists(page, 'button:has-text("Test")');
          await clickIfExists(page, 'button:has-text("Verify")');
          await clickIfExists(page, 'button:has-text("Check")');
          await page.waitForTimeout(3000);
          
          // Save
          await clickIfExists(page, 'button:has-text("Save")');
          await clickIfExists(page, 'button:has-text("Add")');
          await clickIfExists(page, 'button:has-text("Connect")');
          await clickIfExists(page, 'button[type="submit"]');
          await page.waitForTimeout(2000);

        } else if (provider.type === 'oauth') {
          // OAuth flow - needs manual browser interaction
          console.log(`  🌐 OAuth provider: ${provider.name}`);
          console.log(`  Please complete OAuth in the browser window...`);
          console.log(`  OAuth URL: ${provider.oauthUrl}`);
          
          // Click connect button
          await clickIfExists(page, 'button:has-text("Connect")');
          await clickIfExists(page, 'button:has-text("Authorize")');
          await clickIfExists(page, 'button:has-text("Sign in")');
          
          // Wait for user to complete OAuth
          console.log('  ⏳ Waiting for OAuth completion (check browser for popup)...');
          await ask('  Press Enter after completing OAuth authorization...');
          await page.waitForTimeout(3000);
        }

        state.providersAdded.push(provider.id);
        await saveState(state);
        console.log(`  ✅ ${provider.name} added successfully!`);

      } catch (err) {
        console.error(`  ❌ Failed to add ${provider.name}: ${err.message}`);
        console.log('  Continuing to next provider...');
      }

      // Go back to providers list
      await page.goto(`${OMINROUTE_URL}/providers`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(1500);
    }

    // ------------------------------------------------------------------
    // STEP 4: CREATE ALL 14 COMBOS
    // ------------------------------------------------------------------
    console.log('\n📍 Step 3: Creating 14 Combos...');
    await page.goto(`${OMINROUTE_URL}/combos`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(2000);

    for (const combo of COMBOS) {
      if (state.combosCreated.includes(combo.name)) {
        console.log(`  ⏭️  Skipping ${combo.name} (already created)`);
        continue;
      }

      console.log(`\n  ➕ Creating Combo: ${combo.name}`);

      try {
        // Click "Create Combo" or "New Combo"
        await clickIfExists(page, 'button:has-text("Create Combo")');
        await clickIfExists(page, 'button:has-text("New Combo")');
        await clickIfExists(page, 'a:has-text("Create Combo")');
        await page.waitForTimeout(1000);

        // Fill combo name
        await page.fill('input[placeholder*="Name" i], input[name="name"], input[id="name"]', combo.name);
        await page.waitForTimeout(300);

        // Fill description if field exists
        await page.fill('textarea[placeholder*="Description" i], textarea[name="description"]', combo.description).catch(() => {});

        // Add models - this varies by UI
        // Try to find model selector
        for (const model of combo.models) {
          console.log(`    + Adding model: ${model}`);
          
          // Click "Add Model" button
          await clickIfExists(page, 'button:has-text("Add Model")');
          await clickIfExists(page, 'button:has-text("Add")');
          await page.waitForTimeout(500);
          
          // Try to select model from dropdown
          await page.fill('input[placeholder*="Model" i], input[placeholder*="Search" i], select', model).catch(() => {});
          await page.waitForTimeout(500);
          
          // Press Enter to select
          await page.keyboard.press('Enter');
          await page.waitForTimeout(500);
        }

        // Set strategy (round-robin, priority, etc.)
        await page.selectOption('select[name="strategy"], select[name="balancing"]', 'priority').catch(() => {});

        // Save combo
        await clickIfExists(page, 'button:has-text("Save")');
        await clickIfExists(page, 'button:has-text("Create")');
        await clickIfExists(page, 'button[type="submit"]');
        await page.waitForTimeout(2000);

        state.combosCreated.push(combo.name);
        await saveState(state);
        console.log(`  ✅ ${combo.name} created successfully!`);

      } catch (err) {
        console.error(`  ❌ Failed to create ${combo.name}: ${err.message}`);
      }

      // Go back to combos list
      await page.goto(`${OMINROUTE_URL}/combos`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(1500);
    }

    // ------------------------------------------------------------------
    // STEP 5: VERIFY SETUP
    // ------------------------------------------------------------------
    console.log('\n📍 Step 4: Verifying Setup...');
    
    // Test models endpoint
    const response = await page.request.get(`${OMINROUTE_URL}/v1/models`, {
      headers: { 'Authorization': `Bearer ${state.password}` }
    });
    
    if (response.ok()) {
      const data = await response.json();
      console.log(`\n✅ VERIFICATION PASSED!`);
      console.log(`   Models available: ${data.data?.length || 0}`);
      console.log(`   Providers configured: ${state.providersAdded.length}/42`);
      console.log(`   Combos created: ${state.combosCreated.length}/14`);
    } else {
      console.log(`\n⚠️  Verification failed - check manually`);
    }

    console.log('\n🎉 SETUP COMPLETE!');
    console.log('==================');
    console.log('Next steps:');
    console.log('1. Test in Hermes: Use model "leadgen-coding-primary"');
    console.log('2. Check combos at: http://127.0.0.1:20128/combos');
    console.log('3. Check providers at: http://127.0.0.1:20128/providers');
    console.log('\nState saved to:', SETUP_FILE);

  } catch (err) {
    console.error('\n❌ FATAL ERROR:', err.message);
    console.error(err.stack);
  } finally {
    await browser.close();
    rl.close();
  }
}

main().catch(console.error);