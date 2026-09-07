> Verbatim API reference for the coordinator endpoints. See SKILL.md for the core workflow.

## API Reference

### Sequential Coordination
```bash
POST /api/agents/coordinate
{
  "goal": "string (required)",
  "execute": boolean (default false),
  "max_steps": int (default 5, cap 8)
}
```

Returns: `{ok, run_id, goal, plan, results, summary}`

### Parallel Fan-Out
```bash
POST /api/agents/fan-out
{
  "goal": "string",
  "agents": ["dev", "isha", "kavya"] (optional, default 4),
  "max_agents": int (default 4)
}
```

Returns: `{ok, goal, mode="parallel", agents, results, summary}`

### Hierarchical
```bash
POST /api/agents/coordinate-hierarchical
{
  "goal": "string",
  "execute": boolean (default false)
}
```

Returns: `{ok, run_id, goal, pattern="hierarchical", teams, summary}`

### Advanced (Reflexion)
```bash
POST /api/agents/coordinate-advanced
{
  "goal": "string",
  "execute": boolean (default false),
  "max_iterations": int (default 2, cap 3),
  "quality_bar": float (default 0.7, range 0-1),
  "max_steps": int (default 4)
}
```

Returns: `{ok, run_id, goal, pattern="reflexion", iterations, final_score, critique, results, summary, memory_used}`

### List Recent Runs
```bash
GET /api/agents/runs?limit=20
```

Returns: `[{run_id, goal, mode, summary, at}, ...]`

### Roster
```bash
GET /api/agents/roster
```

Returns: `[{id, name, title, duties, executable}, ...]`

