---
name: skill-creator
description: >
  Guide for creating effective skills. This skill should be used when users want
  to create a new skill (or update an existing skill) that extends Verdent's
  capabilities with specialized knowledge, workflows, or tool integrations.
  Covers skill structure, writing SKILL.md, bundling scripts and references,
  packaging, description optimization, validation, and iterative improvement.
icon_dark: './assets/icon-dark.png'
icon_light: './assets/icon-light.png'
metadata:
  version: '3.0.3'
---

# Skill Creator

This skill provides guidance for creating effective skills.

## About Skills

Skills are modular, self-contained packages that extend Verdent's capabilities by providing
specialized knowledge, workflows, and tools. Think of them as "onboarding guides" for specific
domains or tasks—they transform Verdent from a general-purpose agent into a specialized agent
equipped with procedural knowledge that no model can fully possess.

### What Skills Provide

1. Specialized workflows - Multi-step procedures for specific domains
2. Tool integrations - Instructions for working with specific file formats or APIs
3. Domain expertise - Company-specific knowledge, schemas, business logic
4. Bundled resources - Scripts, references, and assets for complex and repetitive tasks

## Communicating with the User

Adapt language to match the user's technical level:

- **Non-technical users**: Avoid jargon. Explain concepts plainly. Focus on what the skill will do for them, not how it works internally.
- **Technical users**: Use precise terminology. Discuss implementation details, trade-offs, and architecture decisions directly.

When gathering requirements, ask focused questions. Avoid overwhelming with too many questions at once — start with the most important ones and follow up as needed.

When presenting skill structure or changes, be concrete: show file paths, example snippets, and expected behavior rather than abstract descriptions.

## Core Principles

### Concise is Key

The context window is a public good. Skills share the context window with everything else Verdent needs: system prompt, conversation history, other Skills' metadata, and the actual user request.

**Default assumption: Verdent is already very smart.** Only add context Verdent doesn't already have. Challenge each piece of information: "Does Verdent really need this explanation?" and "Does this paragraph justify its token cost?"

Prefer concise examples over verbose explanations.

### Set Appropriate Degrees of Freedom

Match the level of specificity to the task's fragility and variability:

**High freedom (text-based instructions)**: Use when multiple approaches are valid, decisions depend on context, or heuristics guide the approach.

**Medium freedom (pseudocode or scripts with parameters)**: Use when a preferred pattern exists, some variation is acceptable, or configuration affects behavior.

**Low freedom (specific scripts, few parameters)**: Use when operations are fragile and error-prone, consistency is critical, or a specific sequence must be followed.

Think of Verdent as exploring a path: a narrow bridge with cliffs needs specific guardrails (low freedom), while an open field allows many routes (high freedom).

### Anatomy of a Skill

Every skill consists of a required SKILL.md file and optional bundled resources:

```
skill-name/
├── SKILL.md (required)
│   ├── YAML frontmatter metadata (required)
│   │   ├── name: (required)
│   │   ├── description: (required)
│   │   └── compatibility: (optional, rarely needed)
│   └── Markdown instructions (required)
└── Bundled Resources (optional)
    ├── scripts/          - Executable code (Python/Bash/etc.)
    ├── references/       - Documentation intended to be loaded into context as needed
    └── assets/           - Files used in output (templates, icons, fonts, etc.)
```

#### SKILL.md (required)

Every SKILL.md consists of:

- **Frontmatter** (YAML): Contains `name` and `description` fields (required), plus optional fields like `license`, `metadata`, and `compatibility`. Only `name` and `description` are read by Verdent to determine when the skill triggers, so be clear and comprehensive about what the skill is and when it should be used. The `compatibility` field is for noting environment requirements (target product, system packages, etc.) but most skills don't need it.
- **Body** (Markdown): Instructions and guidance for using the skill. Only loaded AFTER the skill triggers (if at all).

**Metadata Quality:** The `name` and `description` in YAML frontmatter determine when Verdent will use the skill. Be specific about what the skill does and when to use it. Use the third-person (e.g. "This skill should be used when..." instead of "Use this skill when...").

**Writing an Effective Description:**

The `description` field is the most critical metadata — it determines whether Verdent invokes the skill at the right time. A weak description leads to missed invocations or false triggers.

_Description Formula:_

```
This skill should be used when [primary situations]. This includes [specific use cases with trigger keywords], [more use cases], and [edge cases].
```

_Trigger Keywords:_

Include 5 or more keywords that users are likely to mention when they need this skill. These can be technical terms, action verbs, tool names, file formats, or domain-specific vocabulary.

- Bad: `"Helps with CSV files"`
- Good: `"This skill should be used when working with CSV files, including exploring structure, filtering data, selecting columns, transforming files, sorting, joining datasets, or performing tabular data analysis."`

_Length Constraint:_

Keep the description under 1024 characters. A concise, keyword-rich description outperforms a lengthy, vague one.

_Self-Test Checklist:_

To validate a description's effectiveness:

1. Write 5-10 realistic user queries that should trigger the skill
2. Verify the description contains keywords matching those queries
3. Check for ambiguity with other skills' descriptions
4. Confirm edge cases and alternative phrasings are covered

#### Bundled Resources (optional)

##### Scripts (`scripts/`)

Executable code (Python/Bash/etc.) for tasks that require deterministic reliability or are repeatedly rewritten.

- **When to include**: When the same code is being rewritten repeatedly or deterministic reliability is needed
- **Example**: `scripts/rotate_pdf.py` for PDF rotation tasks
- **Benefits**: Token efficient, deterministic, may be executed without loading into context
- **Note**: Scripts may still need to be read by Verdent for patching or environment-specific adjustments

##### References (`references/`)

Documentation and reference material intended to be loaded as needed into context to inform Verdent's process and thinking.

- **When to include**: For documentation that Verdent should reference while working
- **Examples**: `references/finance.md` for financial schemas, `references/mnda.md` for company NDA template, `references/policies.md` for company policies, `references/api_docs.md` for API specifications
- **Use cases**: Database schemas, API documentation, domain knowledge, company policies, detailed workflow guides
- **Benefits**: Keeps SKILL.md lean, loaded only when Verdent determines it's needed
- **Best practice**: If files are large (>10k words), include grep search patterns in SKILL.md
- **Avoid duplication**: Information should live in either SKILL.md or references files, not both. Prefer references files for detailed information unless it's truly core to the skill—this keeps SKILL.md lean while making information discoverable without hogging the context window. Keep only essential procedural instructions and workflow guidance in SKILL.md; move detailed reference material, schemas, and examples to references files.

Common progressive disclosure patterns for references:

- **High-level guide + references**: SKILL.md contains the workflow overview; detailed methodology, examples, and checklists live in reference files
- **Domain-specific organization**: Group reference files by domain area (e.g., `references/api.md`, `references/schema.md`)
- **Conditional details**: Link to reference files only when specific conditions or edge cases arise

For guidance on structuring skill output, see `references/output-patterns.md`. For workflow design patterns, see `references/workflows.md`.

##### Assets (`assets/`)

Files not intended to be loaded into context, but rather used within the output Verdent produces.

- **When to include**: When the skill needs files that will be used in the final output
- **Examples**: `assets/logo.png` for brand assets, `assets/slides.pptx` for PowerPoint templates, `assets/frontend-template/` for HTML/React boilerplate, `assets/font.ttf` for typography
- **Use cases**: Templates, images, icons, boilerplate code, fonts, sample documents that get copied or modified
- **Benefits**: Separates output resources from documentation, enables Verdent to use files without loading them into context

### Progressive Disclosure Design Principle

Skills use a three-level loading system to manage context efficiently:

1. **Metadata (name + description)** - Always in context (~100 words)
2. **SKILL.md body** - When skill triggers (<5k words)
3. **Bundled resources** - As needed by Verdent (Unlimited\*)

\*Unlimited because scripts can be executed without reading into context window.

## Skill Creation Process

To create a skill, follow the "Skill Creation Process" in order, skipping steps only if there is a clear reason why they are not applicable.

### Step 1: Understanding the Skill with Concrete Examples

Skip this step only when the skill's usage patterns are already clearly understood. It remains valuable even when working with an existing skill.

To create an effective skill, clearly understand concrete examples of how the skill will be used. This understanding can come from either direct user examples or generated examples that are validated with user feedback.

For example, when building an image-editor skill, relevant questions include:

- "What functionality should the image-editor skill support? Editing, rotating, anything else?"
- "Can you give some examples of how this skill would be used?"
- "I can imagine users asking for things like 'Remove the red-eye from this image' or 'Rotate this image'. Are there other ways you imagine this skill being used?"
- "What would a user say that should trigger this skill?"

To avoid overwhelming users, avoid asking too many questions in a single message. Start with the most important questions and follow up as needed for better effectiveness.

Conclude this step when there is a clear sense of the functionality the skill should support.

### Step 2: Planning the Reusable Skill Contents

To turn concrete examples into an effective skill, analyze each example by:

1. Considering how to execute on the example from scratch
2. Identifying what scripts, references, and assets would be helpful when executing these workflows repeatedly

Example: When building a `pdf-editor` skill to handle queries like "Help me rotate this PDF," the analysis shows:

1. Rotating a PDF requires re-writing the same code each time
2. A `scripts/rotate_pdf.py` script would be helpful to store in the skill

Example: When designing a `frontend-webapp-builder` skill for queries like "Build me a todo app" or "Build me a dashboard to track my steps," the analysis shows:

1. Writing a frontend webapp requires the same boilerplate HTML/React each time
2. An `assets/hello-world/` template containing the boilerplate HTML/React project files would be helpful to store in the skill

Example: When building a `big-query` skill to handle queries like "How many users have logged in today?" the analysis shows:

1. Querying BigQuery requires re-discovering the table schemas and relationships each time
2. A `references/schema.md` file documenting the table schemas would be helpful to store in the skill

To establish the skill's contents, analyze each concrete example to create a list of the reusable resources to include: scripts, references, and assets.

### Step 3: Initializing the Skill

At this point, it is time to actually create the skill.

Skip this step only if the skill being developed already exists, and iteration or packaging is needed. In this case, continue to the next step.

When creating a new skill from scratch, always run the `init_skill.py` script. The script conveniently generates a new template skill directory that automatically includes everything a skill requires, making the skill creation process much more efficient and reliable.

Usage (default global):

```bash
scripts/init_skill.py <skill-name>
```

Usage (explicit location override):

```bash
scripts/init_skill.py <skill-name> --path <output-directory>
```

Path rule:

- If user does not specify a location, create the skill under global directory `~/.verdent/skills`
- If user explicitly specifies a location, use the user-provided path exactly

The script:

- Creates the skill directory at the specified path
- Generates a SKILL.md template with proper frontmatter and TODO placeholders
- Creates example resource directories: `scripts/`, `references/`, and `assets/`
- Adds example files in each directory that can be customized or deleted

After initialization, customize or remove the generated SKILL.md and example files as needed.

### Step 4: Edit the Skill

When editing the (newly-generated or existing) skill, remember that the skill is being created for another instance of Verdent to use. Focus on including information that would be beneficial and non-obvious to Verdent. Consider what procedural knowledge, domain-specific details, or reusable assets would help another Verdent instance execute these tasks more effectively.

#### Start with Reusable Skill Contents

To begin implementation, start with the reusable resources identified above: `scripts/`, `references/`, and `assets/` files. Note that this step may require user input. For example, when implementing a `brand-guidelines` skill, the user may need to provide brand assets or templates to store in `assets/`, or documentation to store in `references/`.

Also, delete any example files and directories not needed for the skill. The initialization script creates example files in `scripts/`, `references/`, and `assets/` to demonstrate structure, but most skills won't need all of them.

#### What NOT to Include

Do not include auxiliary documentation or files that are not part of the skill's core functionality:

- README.md, INSTALLATION_GUIDE.md, CHANGELOG.md
- Setup or testing procedures
- User-facing documentation (the skill IS the documentation)
- Files that duplicate information already in SKILL.md or references

#### Update SKILL.md

**Writing Style:** Write the entire skill using **imperative/infinitive form** (verb-first instructions), not second person. Use objective, instructional language (e.g., "To accomplish X, do Y" rather than "You should do X" or "If you need to do X"). This maintains consistency and clarity for AI consumption.

**Size Guideline:** Keep the SKILL.md body under 500 lines. Move detailed content to reference files to maintain lean, focused instructions.

To complete SKILL.md, answer the following questions:

1. What is the purpose of the skill, in a few sentences?
2. When should the skill be used?
3. In practice, how should Verdent use the skill? All reusable skill contents developed above should be referenced so that Verdent knows how to use them.

### Step 5: Packaging a Skill

Once the skill is ready, it should be packaged into a distributable .skill file that gets shared with the user. The packaging process automatically validates the skill first to ensure it meets all requirements:

```bash
scripts/package_skill.py <path/to/skill-folder>
```

Optional output directory specification:

```bash
scripts/package_skill.py <path/to/skill-folder> ./dist
```

The packaging script will:

1. **Validate** the skill automatically, checking:
   - YAML frontmatter format and required fields
   - Skill naming conventions and directory structure
   - Description completeness and quality
   - File organization and resource references

2. **Package** the skill if validation passes, creating a .skill file named after the skill (e.g., `my-skill.skill`) that includes all files and maintains the proper directory structure for distribution.

If validation fails, the script will report the errors and exit without creating a package. Fix any validation errors and run the packaging command again.

### Step 6: Iterate

After testing the skill, users may request improvements. Often this happens right after using the skill, with fresh context of how the skill performed.

**Iteration workflow:**

1. Use the skill on real tasks
2. Notice struggles or inefficiencies
3. Identify how SKILL.md or bundled resources should be updated
4. Implement changes and test again

**Key improvement principles:**

- **Generalize from feedback**: When a user reports a specific failure, fix the general class of problem rather than just the specific instance. A skill that only handles the exact reported case will break on the next variation.
- **Keep the prompt lean**: Resist the urge to add lengthy explanations for every edge case. Each addition competes for context window space. Prefer concise rules over verbose descriptions.
- **Explain the why, not just the what**: When adding instructions, include the reasoning. Verdent follows instructions better when it understands the motivation behind them.
- **Avoid overfitting**: Do not add narrow fixes that only address a single test case. Instead, identify the underlying principle and express it generally.
- **Test with diverse inputs**: After making changes, verify the skill works across a range of realistic scenarios, not just the one that prompted the change.
