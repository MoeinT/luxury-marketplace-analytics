# AI usage

**Tool:** GitHub Copilot in VS Code.

| Task | Copilot assistance | My decisions and validation |
|---|---|---|
| 1 — Analysis | Helped scaffold the CSV analysis and draft summaries of close drift, event quality, and status transitions. | Ran and checked the analysis; caught April's 41.4% event coverage at close and kept its replay out of the representative headline. Treated replay as an estimate, not Finance ground truth. |
| 2 — Design | Helped draft the dbt layers, history approach, metric contracts, and close policy. | Kept Finance's frozen close separate from Operations' live net GMV; specified point-in-time versus current-state semantics and documented assumptions requiring Finance sign-off. |
| 3 — Cycle | Helped reason through the DAG cycle and scaffold the refactor and regression tests. | Derived order-time features from prior orders, separated current buyer state, rejected hidden hard-coded dependencies, and reviewed and verified the SQL and test logic with a PostgreSQL dbt build. |
| 4 — Presentation | Helped organize the presentation outline and draft options, costs, and supporting evidence. | Checked claims against the analysis, kept the cycle section brief, and made uncertainty explicit. |

The assignment materials and data are synthetic; no employer or personal
information was used.
