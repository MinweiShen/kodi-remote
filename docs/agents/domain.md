# Domain Docs

This repository uses a single-context domain-documentation layout.

## Before exploring, read these

- `GLOSSARY.md` at the repository root
- Relevant ADRs under `docs/adr/`

If these files do not exist, proceed silently. Domain-modeling skills create them lazily when terminology or decisions are resolved.

## File structure

```
/
├── GLOSSARY.md
├── docs/
│   └── adr/
├── remote-touchpad/
├── AGENTS.md
└── README.md
```

## Use the glossary's vocabulary

When naming a domain concept in an issue, proposal, hypothesis, or test, use the term defined in `GLOSSARY.md`. Avoid synonyms that the glossary explicitly rejects.

If a needed concept is absent, reconsider whether it belongs to the project vocabulary or note the gap for the domain-modeling workflow.

## Flag ADR conflicts

If proposed work contradicts an existing ADR, identify the conflict explicitly rather than silently overriding the decision.
