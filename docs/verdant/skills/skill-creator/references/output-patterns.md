# Output Patterns

## Template Pattern

Use predefined templates to structure output consistently.

### Strict Templates

Use for outputs requiring consistency (APIs, data formats, formal reports):

- Specify "ALWAYS use this exact template"
- Include all required sections with clear placeholders

Example:

```
## Executive Summary
[1-2 paragraph summary]

## Key Findings
- Finding 1
- Finding 2

## Recommendations
1. [Action item]
```

### Flexible Templates

Use when adaptation adds value:

- Present a "sensible default" structure
- Explicitly permit customization ("use your best judgment")
- Encourage tailoring to context

## Examples Pattern

Provide input/output pairs to demonstrate desired output quality.

**When to use:**

- Output quality depends on understanding style, tone, or format
- Description alone is insufficient

**Structure:**

- Show 2+ concrete examples
- Label clearly (Input -> Output)
- Include brief explanation of the pattern

Example:

```
Input: "Fix the login timeout bug"
Output: "fix(auth): resolve session timeout after 30min idle"

Input: "Add dark mode support"
Output: "feat(ui): add dark mode toggle with system preference detection"
```

**Key principle:** Examples are more effective than descriptions for teaching Verdent the desired output style and level of detail.
