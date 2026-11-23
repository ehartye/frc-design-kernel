# Contributor rules

Short rules for people and coding agents who change this library. The reasons are in [DESIGN.md](DESIGN.md).

## Keep it lean

- No module over **600 lines**. No function over **120 lines**. No circular imports. Tests enforce all three.
- Aim far below the ceilings. One small module does one job.
- The only dependency is `cadquery-ocp`. Everything else is the standard library.
- Scope is **build, measure, try**. Do not add guidelines, pass or fail verdicts, receipts, review pages, publishing
  or CI policy. Tools that judge a design own those.

## Keep it neutral

- No game, season, team or project names. No paths from anyone's machine. No mention of any agent plugin.
- Fixtures and examples are invented. They must not copy a real robot or field.
- Do not import a consumer project, and do not write code that only one consumer needs.

## Know the period

- The library is in the **settling** period: breaking changes are allowed and expected.
- Do not add compatibility shims, deprecation paths or version gates during settling.
- Never make the library read back its own version to allow or refuse work. Version and commit are information only.
- Consumers install from `main` and do not pin. Do not tell a consumer to pin.

## Tests

- Every test names **the failure it catches** in its docstring.
- Every kind of check has a **control**: a test showing the check can fail.
- Keep the suite fast: about a minute for everything.
- Run: `python -m unittest discover -s tests -t .`

## The escape hatch

- Custom shapes follow the contract in DESIGN.md section 6, and custom trial code the one in section 13.6. Do not
  widen either without the owner's say.
- Custom trial code never replaces the control, the brackets or the half-step repeat.
- A new built-in shape is better than a custom shape that two projects both wrote.

## Git

- Never commit on `main`. Work on a feature branch, in a worktree.
- Small pull requests. Squash-merge when checks pass.
- Write plainly: short sentences, and explain any word a high-school student would not know.
