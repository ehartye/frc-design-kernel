# Contributor rules

Short rules for people and coding agents who change this library. The reasons are in [DESIGN.md](DESIGN.md).

## Keep it lean

- No module over **600 lines**. No function over **120 lines**. No circular imports. Tests enforce all three.
- Aim far below the ceilings. One small module does one job.
- The only dependency is `cadquery-ocp`. Everything else is the standard library. MuJoCo is an optional extra:
  only `trials/mujoco_run.py` may import it, and nothing may need it unless a trial names that engine.
- Contact forces are the library's own law in every engine. Never map a material's spring onto an engine's native
  soft contact. An added engine goes into `ENGINES` in `tests/trial_cases.py` and must pass the whole calibration
  set, the squeeze case included; an engine that runs pieces in 3D also goes into `ENGINES_3D` and must seat the
  standing seating case (DESIGN.md section 16).
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
- Custom trial code never replaces the control, the ranges or the half-step repeat.
- Physical inputs belong in the design source with their source (`measured` or `assumed` with a range), in physical
  units. Numbers that only one engine understands go under that engine's own heading.
- What is asked is measured, every time. Nothing works out what changed to decide what to measure or try, or whether
  an earlier answer stands: no fingerprints, no lists of what an answer used, no reading of earlier records. A record
  keeps the question, the answer and the library version, and no date. A measurement of only part of a job is returned
  and never written over a full record.
- A measure or engine that can take more than a moment says how far it is through the meter it is given.
- A new built-in shape is better than a custom shape that two projects both wrote.

## Git

- Never commit on `main`. Work on a feature branch, in a worktree.
- Small pull requests. Squash-merge when checks pass.
- Write plainly: short sentences, and explain any word a high-school student would not know.
