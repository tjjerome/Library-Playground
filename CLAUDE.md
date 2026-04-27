# Library-Playground

Sandbox for experiments. Read source on demand — don't preload docs here.

## Model routing
- Architecture, debugging, security review: Opus
- Implementation, standard coding: Sonnet
- File search, exploration, formatting, renaming: Haiku (use the `researcher` sub-agent)

## Conventions
- Default to Sonnet; only escalate to Opus when reasoning is the bottleneck.
- Use `offset`/`limit` on Read for large files.
- Run `/compact` at logical breakpoints (~60–70% context) instead of letting auto-compact fire.
