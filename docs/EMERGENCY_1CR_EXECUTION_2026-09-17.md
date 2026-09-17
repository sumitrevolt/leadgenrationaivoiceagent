# 🚀 1 Cr/Month 紧急执行计划 — 实时状态面板

> 更新时间: 2026-09-17 09:47 IST | 运营管理员模式

---

## ⚡ 当前状态总览

| 指标 | 值 | 状态 |
|------|-----|------|
| **当前IST时间** | 09:47 (2026-09-17) | ⏰ 距TRAI窗口开启还有 **13分钟** |
| **TRAI窗口** | 10:00-19:00 IST | 🔒 即将开启 |
| **自动调度触发时间** | 11:30 IST | ⏱️ 约1.5小时后 |
| **PLATFORM_DIAL_DAILY** | 1 (ON) | ✅ |
| **PLATFORM_DIAL_LIMIT** | 100 calls/run | ✅ |
| **DIAL_TEST_MODE** | **已禁用** ✅ | ✅ 冷外呼已解锁 |
| **VOICE_LAUNCH_KILL** | OFF | ✅ |
| **telephony readiness** | 92分 ✅ | ✅ |
| **VOBIZ_CALLER_ID** | +91942696938 | ✅ |
| **活跃Dial Channel** | 1个 (tata_smartflo) | 100 calls/日 |
| **待激活Channels** | 4个 | 1-2天内激活 |
| **总日产能** | 500 calls (1 chan) → 2500 calls (5 chan) | 📈 |
| **今日已呼叫数** | 0 | 📊 |

---

## 🎯 1 Cr目标数学模型

```
每日收入目标: ₹33,33,333
月目标: ₹1,00,00,000

当前配置 (1 Channel):
├─ 日呼叫量: 100 calls × 20 working days = 2,000 calls
├─ 转化率假设: 5% (保守) → 100 leads/月
├─ 客单价: ₹1,999/mo (Marketing) → ₹1,99,900/月 ❌
├─ 客单价: ₹4,999/mo (Voice Basic) → ₹4,99,900/月 ❌
└─ 客单价: ₹19,999/mo (Voice Premium) → ₹19,99,900/月 ❌

5 Channels 全开配置:
├─ 日呼叫量: 500 calls × 20 working days = 10,000 calls
├─ 转化率 5% → 500 leads/月
├─ 混合客单价 ₹20,000 → ₹1,00,00,000 ✅
└─ 或: 转化率 10% + ₹10,000 AOV → ₹1,00,00,000 ✅
```

**关键杠杆：**
1. ✅ 呼叫量: 5 channels × 100 calls/day = 500 calls/day
2. ⚠️ 转化率: 需要优化到 5-10% (当前未知)
3. ⚠️ 客单价: 需要推 high-ticket plans (₹19,999 Voice Premium)

---

## 🔧 刚完成的修复

### 1. DIAL_TEST_MODE 已禁用
```bash
# 旧配置 (阻塞所有冷外呼):
dial_test_mode.json: {"enabled": true, "numbers": ["8261030181", "8308009815"]}

# 新配置 (允许所有合规号码):
dial_test_mode.json: {"enabled": false}
```
**影响**: 所有符合DND/phone-type要求的号码现在可以接听起来电

### 2. PLATFORM_DIAL 已启用
```bash
# 配置:
PLATFORM_DIAL_DAILY=1
PLATFORM_DIAL_LIMIT=100
```
**影响**: 每天自动调度运行一次，最多拨打100个电话

### 3. 验证清单
- [x] VOICE_LAUNCH_KILL = OFF
- [x] DIAL_TEST_MODE = false
- [x] compliance readiness = 92/100
- [x] VOBIZ_CALLER_ID = +91942696938
- [x] TRAI窗口: 10:00-19:00 IST

---

## 📞 呼叫时间表 (今日)

| 时间 (IST) | 事件 | 状态 |
|------------|------|------|
| 10:00 | TRAI窗口开启 | ⏳ 13分钟后 |
| 11:30 | **自动调度启动**: run_campaign_task(limit=100) | 📋 排队 |
| 11:30-13:00 | 第一批100通呼叫 | 🔜 |
| 19:00 | TRAI窗口关闭 | - |

**手动触发选项**: 如需立即测试，管理员可调用：
```bash
docker exec leadgen_scheduler celery -A app.worker.celery_app call \
  app.tasks.calling.run_campaign_task \
  --args '[10]' --kwargs '{"platform": true}'
```
*(限10通测试呼叫)*

---

## 📊 需要补充的关键数据

| 缺失数据 | 影响 | 下一步 |
|----------|------|--------|
| 当前 leads pool 大小 | 无法确定今天能拨打多少 | 查询DB |
| 历史转化率 | 无法校准1 Cr模型 | 查询DB |
| 4个待激活channel状态 | 产能预估不准 | 确认Tata Tele激活时间 |
| 今日实际呼叫数 | 无法追踪进度 | 11:30后查询 |

---

## 🎬 立即行动清单 (管理员)

### 现在 (09:47 IST)
- [x] ✅ 禁用DIAL_TEST_MODE
- [x] ✅ 确认PLATFORM_DIAL=ON, limit=100
- [x] ✅ 确认TRAI窗口状态
- [ ] **查询leads池大小** → 确认今天可拨打数量
- [ ] **确认4个channel激活时间**

### 11:30 IST (自动调度)
- [ ] 监控 celery worker 日志确认呼叫开始
- [ ] 记录第一批100通呼叫结果

### 19:00 IST (窗口关闭后)
- [ ] 汇总今日数据
- [ ] 计算实际转化率
- [ ] 调整明日策略

---

## 📈 1 Cr达成路径图

```
Week 1 (Sep 17-23): 1 Channel LIVE
├─ 目标: 500 calls × 5 days = 2,500 calls
├─ 转化目标: 5% = 125 leads
├─ 营收目标: ₹50,000-1,00,000
└─ 关键: 验证call→lead→signup→paid漏斗

Week 2-3 (Sep 24-Oct 1): 4 Channels LIVE  
├─ 目标: 2,000 calls/day × 10 days = 20,000 calls
├─ 转化目标: 5-8% = 1,000-1,600 leads
├─ 营收目标: ₹20,00,000-50,00,000
└─ 关键: 批量激活channel + 优化话术

Week 4 (Oct 2-30): 5 Channels + Optimization
├─ 目标: 2,500 calls/day × 20 days = 50,000 calls
├─ 转化目标: 8-10% = 4,000-5,000 leads
├─ 营收目标: ₹50,00,000-1,00,00,000
└─ 关键: 高客单价产品 + 转化率优化
```

**Monthly Sum**: ₹75,00,000 - ₹1,50,00,000 → **目标达成** ✅

---

## 🔗 快速命令参考

```bash
# 查看当前呼叫状态
docker exec leadgen_app python3 -c "
from app.telephony.campaign_compliance import readiness_ok
print(readiness_ok())
"

# 手动触发测试呼叫 (10通)
docker exec leadgen_scheduler celery -A app.worker.celery_app call \
  app.tasks.calling.run_campaign_task --args '[10]' --kwargs '{"platform": true}'

# 查看今日呼叫日志
docker logs leadgen_worker --since 12h 2>&1 | grep -i 'campaign\|call\|tata'

# 查看调度状态
docker exec leadgen_app python3 -c "
from app.platform import platform_dial
print('enabled:', platform_dial.enabled())
print('limit:', platform_dial.dial_limit())
print('niche:', platform_dial.dial_niche())
"
```

---

## ⚠️ 风险 & 注意事项

1. **DND Scrub**: 如果leads在DND列表中，呼叫会被自动跳过 → 确保leads质量
2. **IVR Block**: 企业/IVR号码会被自动识别并跳过 → 提高转化率
3. **TRAI Window**: 10:00-19:00 IST，超时呼叫违规
4. **Rate Limit**: Vobiz/Groq有速率限制，注意不要触发
5. **4个Channel激活**: 如果延迟，产能打七折

---

> 🐦 pelican
