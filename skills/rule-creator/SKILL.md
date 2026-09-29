---
name: rule-creator
description: Creates or edits a rule or a piece of knowledge to remember, and puts it where Claude Code will load it, whether that is a `.claude/rules/` file, the document that explains a command, or the `CLAUDE.md` of a folder. Use it when a mistake is likely to repeat, or when Claude is likely to make the mistake again because the context that would prevent it is missing (a pitfall, a hidden constraint, a decision whose reason is not visible in the code). Also use it for instructions like "from now on, when you edit X, do Y". Example requests: add a rule, remember this, write this in CLAUDE.md, always do X when you change Y.
---

# Create a rule

`<plugin>` is the plugin root, two levels above this SKILL.md.

Working rules live in three kinds of places: the root `CLAUDE.md` (loaded every session), `.claude/rules/*.md` (rules per topic), and the `CLAUDE.md` of a folder (loaded when Claude reads files in that folder). The root `CLAUDE.md` takes context in every session, so keep it short. Put rules and knowledge with a limited scope where only the work that needs them will load them.

## 1. Write the rule generally

Before choosing a place, rewrite what the user asked for. Users tend to state the case they just ran into, such as "don't use `foo()` in `bar.ts`". A rule that names one case protects one case. The next case of the same kind, say `foo()` in `baz.ts` or `qux()` in `bar.ts`, is not covered, and the same mistake comes back.

State every rule as "in this kind of situation, do X". Follow these steps:

1. **Find the principle the instruction is an instance of.** Ask why the user gave it. What goes wrong if it is ignored, and which other situations go wrong in the same way? The answer is the rule.
2. **Name the whole class of cases.** Replace the single file, function, or value with the category it belongs to: a kind of file, a kind of operation, a kind of input. Then state what to do in that category.
3. **Check whether an existing general rule already covers it.** Read the existing rules (section 3). If a general rule covers the case, do not add a new one. At most, add the case to it as an example. If a rule covers a wider or narrower class, widen it or merge into it.
4. **Keep the specific case only as a short example**, and only if it makes the rule easier to apply. The example must not be the rule itself.
5. **If you cannot name the principle, ask the user** what they want to prevent, then write the rule from the answer.

Example of the same instruction written badly and well:

```markdown
<!-- Bad: covers one case -->
- Do not use `fetchUser()` in `src/api/users.ts`; it skips the cache.

<!-- Good: covers the class, keeps the case as an example -->
- Read data through the cached client wrappers in `src/api/cache/`, not the raw
  request functions. Raw requests skip the cache and cause duplicate calls.
  Example: use `cachedFetchUser()`, not `fetchUser()`.
```

The good version covers every current and future endpoint, states the reason, and points to a place that can be checked.

## 2. Choose where to write it

| Content | Where to write it |
| ------- | ----------------- |
| A fact needed for every task (commands, overall structure, absolute rules) | Root `CLAUDE.md`. Keep it short, under `maxDocLines` lines (default 200). |
| A rule about one topic that matters whichever file is touched | `.claude/rules/<topic>.md` without `paths` |
| A rule that applies only when reading, editing, or deleting specified files or a kind of file | `.claude/rules/<topic>.md` with `paths` (the default choice) |
| A rule that applies when running a command | The document that explains that command (see below) |
| A rule that applies when working inside one folder | The `CLAUDE.md` at that folder's root, in the notes section (see below) |
| A multi-step procedure, or a way of working that is only needed on demand | A skill: `.claude/skills/<name>/SKILL.md` |
| The role of a folder | The role section of that folder's `CLAUDE.md` (managed by librarian, not by this skill) |

If it is unclear where a rule belongs, choose a rule file with `paths`. A narrow scope keeps the rule out of the context of unrelated work.

**A rule for running a command.** Find the document that explains the command: a section of the README or docs, the command's own `SKILL.md`, or a `.claude/commands/` file. Add the rule to that document, next to the description of the command. If no such document exists, ask the user where the rule should go. Do not invent a new place.

**A rule for one folder.**

- Write it in the `CLAUDE.md` at that folder's root, under its notes heading: `## Notes` for English, `## 메모` for Korean, following the library language (`language` in `.librarian/config.json`). A folder document has this section between the role and subfolder sections; add the rule as text under it. Do not create a separate `## Rules` heading. If the notes heading is missing (the library was built with an older version), run `python <plugin>/scripts/librarian.py update` first, or add the heading between the role and subfolder sections yourself. Write the text of the rule in the language given under "Write the file" (section 5).
- Never write inside the block from `<!-- librarian:index:start -->` to `<!-- librarian:index:end -->`. The librarian script rewrites that block, and anything inside it is lost.
- If the folder has no `CLAUDE.md` and the project has `.librarian/config.json`, run `python <plugin>/scripts/librarian.py scaffold` from the project root first. It creates the missing document with the right structure. Then add the rule under its notes heading. If scaffold does not create the document because the folder is excluded from the library, write the rule in a `.claude/rules/` file with `paths` for that folder instead.
- A subfolder's `CLAUDE.md` loads lazily, when Claude reads files in that subfolder. A rule that must be active before any file is read belongs in the root `CLAUDE.md` or a rule file without `paths`.

## 3. Check existing rules before writing

Read every file under `.claude/rules/` (subfolders included), the root `CLAUDE.md`, and the `CLAUDE.md` of the target folder. If a rule on the same topic exists, add to that file instead of creating a new one. Writing the same rule in two places makes the copies drift apart over time, and when they differ nobody can tell which one to follow. When you move content from the root `CLAUDE.md` into a rule file, delete it from `CLAUDE.md` and leave a one-line pointer.

## 4. Split a long document

A long document costs context in every session that loads it, and rules buried in it are followed less reliably. Split it when any of these is true:

- The document is over `maxDocLines` lines (default 200, set as `maxDocLines` in `.librarian/config.json`). This applies to rule files under `.claude/rules/` and to the prose of a folder `CLAUDE.md`, not counting the generated index block.
- The `SessionStart` hook or `python <plugin>/scripts/librarian.py check` reported that the document is too long.
- The rule you are about to add would push the document over the limit. Split first, then add the rule to the right new place.

How to split:

1. **Group the content by topic and generality.** Each group covers a whole class of cases (see section 1), not one case per file. Do not cut at an arbitrary line count or create one file per rule.
2. **Move each topic to its own place**, chosen with the routing table in section 2: a `.claude/rules/<topic>.md` with `paths` when the rule applies to certain files; the notes section of the subfolder's `CLAUDE.md` when it applies to one folder; the command's own document when it applies to a command. Keep each new file to one topic.
3. **Leave one line per moved topic in the original**: a short summary and a pointer to the new place. The original stays a complete overview, and the details live in one place only.
4. **Never duplicate text.** Move it; do not copy it. Two copies drift apart, and nobody can tell which one to follow.
5. **Update every pointer** that named the old location (other documents, the list of rule files if the project keeps one), so that none breaks.
6. **Do not touch the generated files**: the index block between `<!-- librarian:index:start -->` and `<!-- librarian:index:end -->`, `index.md`, and the `index/` folder. The script owns them and splits long indexes on its own.
7. **Verify** with `python <plugin>/scripts/librarian.py check`. The document must no longer be reported as too long.

## 5. Write the file

Name the file after its topic in English kebab-case, for example `error-handling.md`. Keep one topic per file. Rule files may be grouped into subfolders of `.claude/rules/`, which are read recursively.

A rule limited to certain files starts with YAML frontmatter. Use single quotes:

```markdown
---
paths:
  - 'src/api/**/*.ts'
  - 'config/api.json'
---

# API rules

...
```

How `paths` works (official documentation: https://code.claude.com/docs/en/memory):

- A path-scoped rule loads when Claude **reads** a file that matches a pattern. The documentation describes only reads. It does not state that the rule also loads when Claude creates, edits, or deletes a file without reading it first. So for a rule about creating files, also list files that Claude will certainly read before that work, such as other files in the same folder or a related config file.
- Paths are globs relative to the project root. `**` matches any number of folder levels, and `{ts,tsx}` matches several extensions.
- If `paths` is missing, or the YAML in the frontmatter is broken, the rule loads in every session. A broken frontmatter silently turns a scoped rule into a global one, so check it.

Follow these principles in the body:

- **Be specific enough to check.** Write "wrap every raw request in `withRetry()` from `src/api/retry.ts`", not "handle errors well". General does not mean vague: name the class of cases and the exact action.
- **Give each rule a one-sentence reason.** The reason lets someone judge later whether the rule is still needed, and tells Claude how to handle a case the rule did not foresee.
- **Do not restate what the code shows**, such as folder listings or function lists. Write what the code cannot tell: pitfalls, background, decisions.
- **Give locations as paths**, such as `src/api/retry.ts`, so they can be opened directly.

Write the text of the rule in the library language (`language` in `.librarian/config.json`) if the project has that file. Otherwise, use the language the user wrote in.

## 6. Wrap up

1. If the project keeps a list of rule files, for example a table in the root `CLAUDE.md`, add a line for the new file with its scope.
2. If the file you wrote or edited is now over `maxDocLines` lines, split it (section 4).
3. If the project defines a markdown formatter or linter (in `package.json` scripts, a Makefile, or a rule file about markdown), run it on the changed files and make it pass.
4. Report to the user which file you wrote and what scope it applies to, and how you generalized the rule if it differs from what they said. If you split a document, say which topics moved where.
5. Tell the user how to verify loading: open a file that matches the scope, then run `/context` and look at the memory files list.
