# Storage paths

Nyrobrain runs in two environments — a Linux cloud pod and the macOS
desktop app's local mode — and both back the workspace with a network
filesystem (S3 Files via NFS in the pod, rclone+macFUSE on the Mac).
Many-small-file ops on those mounts are 100–2000x slower than on
ordinary local disk. To keep `uv sync`, `DataLoader` writes, and
build outputs fast, we route ephemeral data to local disk via a set
of env vars. User code should read those env vars instead of
hardcoding paths.

## The env vars

| Var | Cloud pod | Desktop local mode | Durable? | Purpose |
|---|---|---|---|---|
| `NYROBRAIN_WORKSPACE` | `/workspace` | the workspace folder you picked at desktop launch | yes, network-backed | Source code, notes, anything you want to keep across restarts and see from the other environment |
| `NYROBRAIN_DATA_DIR` | `/root/.nyrobrain/-workspace/data` | `~/.nyrobrain/<workspace-slug>/data` | **no — ephemeral** | Data-loader cache. Fast local disk. Wiped on pod restart / Mac reboot. Re-downloadable on cache miss. |
| `UV_PROJECT_ENVIRONMENT` | `/root/.nyrobrain/-workspace/venvs/workspace` | `~/.nyrobrain/<workspace-slug>/venvs/workspace` | **no — ephemeral** | Python virtualenv. `uv` reads this; `uv sync` recreates it if missing. |
| `UV_CACHE_DIR` | `/root/.nyrobrain/cache/uv` | `~/.nyrobrain/cache/uv` | partial — survives sessions on Mac, ephemeral in the pod | uv wheel cache. Slow to repopulate but pure cache. |
| `NYROBRAIN_MCP_DATA_ROOT` | `/root/.nyrobrain/-workspace/mcp` | `~/.nyrobrain/<workspace-slug>/mcp` | **no — ephemeral** | mcp's per-module state (kb.sqlite + embed queue). Must live on local disk so SQLite locks work AND so cloud-pod + desktop don't collide on the same DB. Each side maintains its own independent index of the synced source files. |

`<workspace-slug>` is the absolute path of the workspace with `/`
replaced by `-`, mirroring Claude Code's convention. On desktop,
`/Users/marcus/bq/nyrobrain` becomes `-Users-marcus-bq-nyrobrain`.
On the cloud pod the workspace is always `/workspace`, so the slug
is always `-workspace`. The leading dash is intentional — it falls
out of the deterministic path-to-slug transform and is the same
rule in both environments. Scoping data + venvs per workspace
means switching workspaces (desktop) or moving between pods doesn't
blow away the previous one.

## When to use which

**Use `NYROBRAIN_WORKSPACE`** for anything you want to survive a pod
restart, sync between desktop and cloud, or share with another user:

- Source code (Python, configs, scripts)
- Pipeline outputs you want to keep
- Notes, ADRs, documentation
- Manually-curated datasets

**Use `NYROBRAIN_DATA_DIR`** for the data-loader cache and anything
that's regenerable. This is the directory `DataLoader` writes
downloaded topic chunks to. It's intentionally fast and ephemeral —
treat it as RAM with a longer fuse, not as durable storage.

**Never** use `NYROBRAIN_DATA_DIR` for:

- Code, scripts, plots, images, reports, or any user-facing artifact
- Anything you want the file server (and therefore the chat UI) to
  read or render
- Anything that took manual effort to produce

The file server treats `$NYROBRAIN_DATA_DIR` as off-limits — files
written there cannot be rendered in chat, fetched as images, or
served to the UI.

**Use `UV_PROJECT_ENVIRONMENT`** indirectly — `uv` reads it
automatically. You almost never write to it directly.

**Use `UV_CACHE_DIR`** indirectly — same, `uv` reads it.

## In code

Python pipelines / scripts:

```python
import os
from pathlib import Path

workspace = Path(os.environ["NYROBRAIN_WORKSPACE"])  # durable
data = Path(os.environ["NYROBRAIN_DATA_DIR"])         # fast, ephemeral

# data may not exist on first use — mkdir if your code writes there
data.mkdir(parents=True, exist_ok=True)

# DataLoader usage
from adrs import DataLoader
loader = DataLoader(
    topics=topics,
    data_dir=str(data),
)
```

Shell:

```bash
mkdir -p "$NYROBRAIN_DATA_DIR/run-$(date +%s)"
uv run python backtest.py --out "$NYROBRAIN_DATA_DIR/run-..."
```

If you want a final result to persist:

```bash
# At end of run, move the things you want to keep into the workspace
mv "$NYROBRAIN_DATA_DIR/run-foo/final-report.parquet" \
   "$NYROBRAIN_WORKSPACE/brain/strategy/foo/final-report.parquet"
```

## Why this exists

Without this split, `uv sync` and `DataLoader` cache writes happen
directly on s3files / rclone+S3, which means:

- `uv sync` of `numpy + pandas + scipy` (thousands of small files) goes
  from ~10s on local disk to several minutes
- DataLoader writing thousands of topic chunks bottlenecks on per-file
  NFS round-trips
- `rm -rf outdir/` on s3files can take 8+ minutes for 10k files

Routing the ephemeral parts to pod-local NVMe (cloud) or Mac APFS
(desktop) restores expected developer-loop speed while keeping
durable state on the synced workspace.

## Migration from the old `outdir/` convention

Older code hardcoded `data_dir=PROJECT_ROOT / "outdir"`. Update it to
read `$NYROBRAIN_DATA_DIR` so pipelines run fast in both environments.
The new path is on pod-local disk, so existing data in
`$NYROBRAIN_WORKSPACE/outdir/` is not migrated — it's a cache, just
let DataLoader repopulate on next run.
