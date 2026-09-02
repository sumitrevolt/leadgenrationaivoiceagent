# Runtime-data cutover

`scripts/_runtime_data_guard.sh` points operators here when it refuses a deploy. Until 2026-07-28 this file did not exist, so the refusal named a document nobody could read. This is that document.

## Why every deploy is refused

`scripts/deploy_vps.sh` runs `git pull --ff-only` inside `/opt/leadgen` — the live checkout. That directory also holds production mutable state: **186 files under `data/` are git-tracked**, including

- `data/delivery_ledger/jiya-makeover.jsonl` — the paying customer's delivery ledger
- `data/content_queue/jiya-makeover.jsonl` — their content queue
- `data/marketing_clients.jsonl` — the customer registry

plus untracked-but-authoritative stores in the same tree (invoice ledger, consent ledger, voice/WhatsApp/email suppression lists, ~182 MB of DPDP call recordings).

So the release's one destructive command operates on the directory holding the compliance record. The guard refuses on manifest state, not on whether a particular diff happens to touch those files — deliberately, because "this release doesn't touch them" is a property of one diff and the guard has to hold for all of them.

**The guard has no bypass variable and no `|| true`. Do not add one.** Its own header says so. If you need to deploy, move the stores.

## What "done" means

`manifest.blocking_stores()` counts every row whose `migration_state` is in `BLOCKING_STATES`. Both `LEGACY_IN_CHECKOUT` **and** `DUAL_READ_PRE_CUTOVER` block. A store stops blocking only at `CUTOVER_COMPLETE`.

So the deploy unblocks when **all** blocking stores reach `CUTOVER_COMPLETE` — not when the code is resolver-ready, and not when the bytes have been copied.

As of 2026-07-28, `scripts/runtime_data_cutover.py status` reports **21 blocking stores**: 6 resolver-ready (`DUAL_READ_PRE_CUTOVER`, waves A1 + A2) and 15 still `LEGACY_IN_CHECKOUT`. Note that the manifest holds **16** `LEGACY_IN_CHECKOUT` rows in total — one of them carries `deployment_blocker=False` and so is not in the 21. Read the count from `status`, not by adding up states by hand; the blocker set is defined by `BLOCKING_STATES` **and** the per-row `deployment_blocker` flag, and only the tool applies both.

## The ordering that is NOT optional

`runtime_data_marker.validate_marker` rejects a marker listing a store that is still `LEGACY_IN_CHECKOUT`. That is not a formality — a store whose code still reads the checkout path cannot be recorded as migrated without creating a split brain. So per wave:

```
1. CODE      migrate the writers/readers to
             runtime_data_authority.resolve_store_path      (reviewed PR)
2. MANIFEST  flip those rows to DUAL_READ_PRE_CUTOVER       (same PR)
             -> blocker count does NOT drop. Resolver-ready is not data-safe.
3. BYTES     scripts/runtime_data_cutover.py plan / copy / verify
4. MARKER    scripts/runtime_data_cutover.py activate
5. MANIFEST  flip those rows to CUTOVER_COMPLETE            (reviewed PR)
             -> blocker count drops by the size of the wave
```

Steps 1, 2 and 5 are code and go through review. Steps 3 and 4 run on the host. The tool deliberately refuses to do 2 or 5 for you, and does not set `RUNTIME_DATA_CUTOVER_ENABLED` — a script running on a production host at 3am is the wrong place to change what the application believes about its own authority.

## Prerequisites on the host

```bash
# 1. an external root OUTSIDE the git checkout, on the same filesystem as the
#    checkout if you can manage it: os.replace() is only atomic within one
#    filesystem, and the atomic-write helpers resolve their temp file against
#    the destination.
mkdir -p /opt/leadgen-runtime
chown -R <app-user>:<app-group> /opt/leadgen-runtime

# 2. bind-mount it into every app-image service in docker-compose.vps.yml
#    (app, worker, scheduler, worker-heavy, worker-video). A root mounted into
#    four of five containers is a split brain, not a migration.
#      volumes:
#        - /opt/leadgen-runtime:/var/lib/leadgen/runtime

# 3. env, in .env — BOTH are needed and they are not the same thing
LEADGEN_RUNTIME_DATA_DIR=/var/lib/leadgen/runtime        # path INSIDE the container
LEADGEN_RUNTIME_DATA_HOST_DIR=/opt/leadgen-runtime       # path on the HOST
```

Leave `RUNTIME_DATA_CUTOVER_ENABLED` unset for now. With a root configured and the gate off, the authority is in `MIGRATION_VALIDATION`: tooling can create and inspect the target, and **live writers do not move**. That is the state you want while copying.

## Running a wave

```bash
cd /opt/leadgen

# read-only: what moves, from where, to where, how big
python scripts/runtime_data_cutover.py plan \
  --stores compliance.wa_suppression compliance.consent_ledger compliance.voice_suppression

# additive copy + sha256 both sides. Sources are never modified or deleted.
python scripts/runtime_data_cutover.py copy --yes \
  --stores compliance.wa_suppression compliance.consent_ledger compliance.voice_suppression

# recompute both sides independently and compare. Non-zero exit on ANY mismatch.
python scripts/runtime_data_cutover.py verify

# marker — only if verify passed in this chain
python scripts/runtime_data_cutover.py activate --yes \
  --rollback-reference <prior production sha> --operator <you>
```

### If `verify` fails with "SOURCE changed since the copy"

A live process appended to the store between `copy` and `verify`. That is the normal case for an active ledger, not a corruption. Either quiesce the writer (stop `worker`/`scheduler`, leave `app` up if you can tolerate it) and re-copy that store with `--resume`, or accept a maintenance window. Do **not** re-run `verify` hoping it passes — the point of that check is that it cannot.

### Quiescing

Tier-0 compliance stores are appended by request handlers and by Celery. For those, stop `worker` and `scheduler` first; a consent write during a copy is the one case where losing an append has a regulatory cost rather than a cosmetic one.

## After the marker

The bytes now exist in two places and the checkout copy is still authoritative, because the gate is off. To finish:

1. Flip the wave's rows to `CUTOVER_COMPLETE` in `app/platform/runtime_data_manifest.py` (reviewed PR, with the marker path cited in the commit message).
2. Set `RUNTIME_DATA_CUTOVER_ENABLED=1`.
3. Re-run `python scripts/runtime_data_preflight.py check-deploy`. It stays DENIED until every blocking store is done.

Once it passes, `scripts/deploy_vps.sh` proceeds through the unmodified guard — which is the whole point.

## Rollback

Nothing to undo until step 2 above: with the gate off, the application never read the new location. After the gate is on, rollback is `RUNTIME_DATA_CUTOVER_ENABLED=0` (authority falls back to `MIGRATION_VALIDATION`, i.e. the checkout copy) plus reverting the manifest commit. **This is why the tool never deletes a source** — deleting the checkout copy is a separate, later decision, taken only once the external root has survived real traffic, and it is the step that makes rollback impossible.

## Do not

- Add a bypass to the guard, or edit the preflight to return fewer blockers. A count that drops without bytes moving is a false green, and the whole control plane exists to prevent exactly that.
- Hand-run `docker compose` to skip the guard. `deploy_vps.sh` is canonical for reasons unrelated to this gate: it enforces mandatory `APP_VERSION`, deploys all five app-image services together to prevent skew, and verifies `/health.version` against the deployed sha. Bypassing it has caused production incidents in this repo before.
- Copy `*.lock` files. The tool skips them and says so. A lock describes a process that is running now; copied to a new root it is a lock nobody holds.
