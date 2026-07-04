---
on:
  workflow_dispatch:

permissions:
  contents: read
  copilot-requests: write


model: claude-opus-4.8

safe-outputs:
  create-issue:
    title-prefix: "[ABC] "
    max: 1
---

# Repository Summary Task

Read this repository's `README.md` (or, if none exists, look at the top-level
files and folders) and write a short, friendly summary of the project:

- 3-5 sentences describing what the project does
- A bullet list of the main technologies/languages used
- One suggestion for a good first thing a new contributor could look at

Create a new issue containing this summary.
