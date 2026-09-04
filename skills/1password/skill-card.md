## Description: <br>
Set up and use 1Password CLI (op). Use when installing the CLI, enabling desktop app integration, signing in (single or multi-account), or reading/injecting/running secrets via op. <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[steipete](https://clawhub.ai/user/steipete) <br>

### License/Terms of Use: <br>


## Use Case: <br>
Developers and operators use this skill to install and operate the 1Password CLI, enable desktop app integration, sign in to the correct account, and safely read, inject, or run commands with secrets. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: Commands or examples can print secrets, disable masking, or write secret material to disk. <br>
Mitigation: Keep 1Password locked until needed, avoid examples that print secrets or use --no-masking, prefer op run or op inject, and protect any files that must contain secret material. <br>
Risk: Using the wrong 1Password account, vault, or item path can expose unintended secrets. <br>
Mitigation: Specify the exact account, vault, and item path, then verify the active account with op whoami before reading or injecting secrets. <br>


## Reference(s): <br>
- [1Password CLI get started](https://developer.1password.com/docs/cli/get-started/) <br>
- [ClawHub skill page](https://clawhub.ai/steipete/skills/1password) <br>
- [get-started.md](references/get-started.md) <br>
- [cli-examples.md](references/cli-examples.md) <br>


## Skill Output: <br>
**Output Type(s):** [text, markdown, shell commands, configuration, guidance] <br>
**Output Format:** [Markdown guidance with inline shell commands and command checklists] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [Requires user-controlled 1Password CLI authentication and an unlocked 1Password app before secret access.] <br>

## Skill Version(s): <br>
1.0.1 (source: server release evidence) <br>

## Ethical Considerations: <br>
Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment. <br>
