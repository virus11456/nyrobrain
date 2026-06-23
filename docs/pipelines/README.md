# Alpha Pipelines

Each pipeline in this folder describes a self-contained recipe for writing
and evaluating a trading alpha: the directory layout, the code shape of
`alpha.py` / `backtest.py`, the `summary.md` template, and the metrics to
report.

File names, column names, and frontmatter keys inside each pipeline are
load-bearing — the dashboard and plot scripts depend on them. Follow the
chosen pipeline exactly.

## Picking a pipeline (agent behavior)

Before writing any strategy, count the pipeline files in this folder
(`docs/pipelines/*.md`, excluding this `README.md`):

- **Exactly one pipeline available** — use it without asking. There is no
  ambiguity to resolve.
- **Two or more pipelines available** — do not guess. Ask the user which
  pipeline to use, listing each pipeline by its title and a one-line
  description pulled from its doc's heading. Wait for the user to pick
  before generating any files.

Do not mix pipelines within a single strategy directory.

## Available pipelines

| # | Pipeline | Description |
| - | -------- | ----------- |
| 1 | [Back/Forward 73-Split](./1-backforward-73split.md) | Single 70/30 time split, in-sample backtest + out-of-sample forward test via `AlphaReportV1`. |
| 2 | [Portfolio](./2-portfolio.md) | Group multiple strategies into one portfolio and backtest. |

## Adding a new pipeline

Add a numbered `N-slug.md` file in this folder. The pipeline doc must
include a complete reference implementation inlined as code blocks at the
bottom (at minimum: `alpha.py`, `backtest.py`, `summary.md`) so the agent
can follow it without needing to read any sibling files.
