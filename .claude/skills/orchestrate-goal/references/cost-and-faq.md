> Verbatim cost summary + FAQ for the 4 automation loops. See SKILL.md for the decision tree.

## Cost Summary

If you run all 4 loops daily:

```
Self-Improve Loop:      $30/day (480 task picks, Groq quota)
Coordinator (10 runs):  $10-15/day (LLM calls)
Process-Engine (3 workflows): $5-10/day (LLM decisions)
Chatbot (ongoing):      ~$5-10/day (LLM inference)
────────────────────────────────
TOTAL:                  ~$50-65/day
```

**Budget**: Groq free tier (~300 calls/day) covers all. Cerebras backup covers spikes.

---

## FAQ

**Q: Can I use multiple loops for the same goal?**
A: Yes! Example: self-improve picks a goal daily, then coordinator executes it (more detailed), then process-engine gates approval. Nested loops are fine.

**Q: What if self-improve loop picks same task daily?**
A: Bandit learns — if task has high success rate, it picks it more. If outcomes decay, bandit will explore other tasks.

**Q: Can I pause the self-improve loop?**
A: Yes, `SELF_IMPROVE_LOOP=0` in .env. Coordinator and process-engine are on-demand (pause manually).

**Q: Which loop is cheapest?**
A: Process-engine (LLM decisions only, no generation). Coordinator is next ($1-4 per run). Self-improve depends on task frequency.

**Q: Which loop learns best?**
A: Coordinator (advanced mode) stores episodic memory. Self-improve learns via bandit success rates. Process-engine doesn't learn (deterministic).
