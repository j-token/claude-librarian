---
name: update-library
description: Brings an existing claude-librarian library up to date with the installed plugin version. Updates the config keys, removes the rules skill links older versions installed, converts AGENTS.md folder documents to CLAUDE.md, and reformats every folder document.
disable-model-invocation: true
---

# Update the library

`<plugin>` is the plugin root, two levels above this SKILL.md. Run every command from the project root.

This updates the library in the project. To update the plugin itself, the user runs `/plugin update` (Claude Code) first.

## 1. Run the update

```bash
python <plugin>/scripts/librarian.py update
```

It does four things:
- Fills in missing keys in `.librarian/config.json` with their defaults (for example `maxDocLines`, the line limit of a document, default 200), removes keys of removed features, and records the current plugin version in `libraryVersion`.
- Removes what older versions installed for the `librarian-guide` rules skill: its links under `.claude/skills`, `.agents/skills`, and `.codex/skills` (and those folders when they end up empty), and their `.gitignore` entries. A copied folder there whose files differ from `.librarian/skills/librarian-guide` is left in place with a `warning`.
- Rewrites every folder document in the current format. Roles that are already written are kept, an empty notes section (`## Notes`, or `## 메모` in Korean) is added to documents that lack one, and the old one-line pointer to the rules skill is removed from the root document. When an index table is longer than `maxDocLines`, it is moved into `index.md` (and further into an `index/` folder) automatically, and levels that are no longer needed are merged back.
- Converts folder documents that older versions wrote as `AGENTS.md` (the `docName` setting, including the `both` mode where `CLAUDE.md` held only `@AGENTS.md`) to `CLAUDE.md`. The folder document is always `CLAUDE.md` now, and the plugin supports only Claude Code.

## 2. Leftover rules skill folder

If the output has a `warning` about `.librarian/skills/librarian-guide` or one of its copies, that folder is no longer used but was left in place, because the user may have added their own text to it. Tell the user; do not delete it on your own.

## 3. Report

Report to the user:
- What was created or updated
- Any `role needed` entries. Offer to fill them in following `<plugin>/skills/rebuild-library/references/cataloger.md`, in the library language.
- Any folder depth warnings (`warning`). Do not restructure folders; only pass them on to the user.
