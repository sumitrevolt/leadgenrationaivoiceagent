# Workflow Patterns

## Sequential Workflows

Use for complex tasks with linear, step-by-step operations.

**Best practices:**

- Provide an overview of the entire process early in SKILL.md
- Number each step clearly
- Include the specific command or tool for each step

**Example structure:**

```
1. [Analysis step] (run tool_a.py)
2. [Configuration step] (edit config_file.json)
3. [Validation step] (run tool_b.py)
4. [Execution step] (run tool_c.py)
5. [Verification step] (run tool_d.py)
```

## Conditional Workflows

Use for tasks with branching logic or multiple paths based on conditions.

**Best practices:**

- Clearly identify decision points
- Use conditional language ("If X, then follow Y workflow")
- Provide separate documented workflows for each branch

**Example structure:**

```
1. Determine the condition
   -> Path A? Follow "Workflow A"
   -> Path B? Follow "Workflow B"

2. Workflow A: [steps]
3. Workflow B: [steps]
```

## When to Use Each Pattern

- **Sequential**: PDF form filling, data processing pipelines, installation procedures
- **Conditional**: Content creation vs. editing, different file types, user choice scenarios
