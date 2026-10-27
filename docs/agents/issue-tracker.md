# Issue tracker: Local Markdown

Issues and specs for this repo live as Markdown files in `.scratch/`.

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`
- The spec is `.scratch/<feature-slug>/spec.md`
- Implementation issues are one file per ticket at `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01`; never use a single combined tickets file
- Triage state is recorded as a `Status:` line near the top of each issue file
- Comments and conversation history append to the bottom under a `## Comments` heading

## When a skill says "publish to the issue tracker"

Create a new file under `.scratch/<feature-slug>/`, creating the directory if needed.

## When a skill says "fetch the relevant ticket"

Read the file at the referenced path. The user will normally provide the path or issue number.

## Wayfinding operations

The map is a file with one child file per ticket.

- Map: `.scratch/<effort>/map.md`
- Child ticket: `.scratch/<effort>/issues/NN-<slug>.md`
- `Type:` records `research`, `prototype`, `grilling`, or `task`
- `Status:` records `claimed` or `resolved`
- `Blocked by: NN, NN` records dependencies
- To find the frontier, scan for open, unblocked, and unclaimed tickets; first by number wins
- To claim a ticket, set `Status: claimed` and save before working
- To resolve a ticket, append its answer under `## Answer`, set `Status: resolved`, and add a context pointer to the map
