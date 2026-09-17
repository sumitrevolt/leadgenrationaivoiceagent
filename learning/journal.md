# PILOT Learning Journal

## 2026-09-17 PILOT cron session (05:15 IST)
- **Lesson 1:** task PLAT-002 14h me evidence-collection par stall raha — pehle jab 4h+ no-ACK mila, turant supersede karna chahiye tha naki 24h baad. Root cause: jab platform ka task BLOCKED ho aur uska root cause sabse critical bottleneck hai, to use aur specific actionable task me replace karna bhi kaafi nahi — usko P0 priority + crisp deadline + expected evidence dena mandatory hai.
- **Lesson 2:** bots ke ACK time track karo — agar 5h+ bina evidence, no-progress, no-ACK hai, to escalate owner ko bina owner-direct blast bot ko reassign karo. PLAT-001 BLOCKED thi 4h+, fir bhi usme hi kaam chalta raha jabki PLAT-002 me swap karna tha.
- **Lesson 3:** VOBIZ credits checking (vobiz_monitor.log) = single point of truth hai for call-loop health. Har 5 min isko check karo — bus 20 entries mat dekho, monotonically banta hua balance=no_creds pattern mat dekho. Admin UI me indicator daalwao if possible.
