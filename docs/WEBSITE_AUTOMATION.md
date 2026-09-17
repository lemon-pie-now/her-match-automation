# Rally49 automation and website split

## Repositories and ownership

- `lemon-pie-now/her-match-automation`: schedule collection, private source settings,
  newsletter generation, and schedule transfer.
- `lemon-pie-now/rally49-website` (private): authoritative website code, public game
  data, checks, and Cloudflare publishing. Read its README for the complete runbook.
- Local website checkout: `rally49-website/` inside this workspace, ignored by this
  repository. It has its own Git history and remote. Open that folder for site work.

The legacy `website/` directory stays here temporarily to keep the existing GitHub
Pages site and event generator working during migration. **Make all new frontend
changes in the new repository.** Continue to generate `website/events.js` here;
that file is the input to the schedule-sync workflow. Do not copy newsletter or
private source data to the new repository.

## Workflows

1. **Update Her Match Events** (`update-events.yml`): scheduled daily at 11:17 UTC;
   can be run manually. Collects data, creates newsletter output, and generates
   `website/events.js`. Existing source secrets remain here.
2. **Sync Rally49 website schedule** (`sync-website.yml`): runs after a successful
   collector run on main, or manually. Checks out latest main from both repositories,
   copies only the public schedule, validates it, and pushes if changed. Uses a
   scoped SSH deploy key so the push starts the website workflow.
3. **Check and publish website** (new repository): runs on main pushes, PRs, or manual
   request. Tests the UI logic and validates event data, then stages exactly four
   public files. Production deployment requires `CLOUDFLARE_ENABLED=true` and credentials.

A failed collector run does not transfer data. A failed validation does not push or
publish. Overlapping sync runs are serialized; ordinary push races are retried.
Public files are allowlisted by the website build script; adding new assets requires
updating that list deliberately.

## Settings

In this repository:
- Actions secret `WEBSITE_DEPLOY_KEY`: SSH private key for the website repository.
- Actions variable `WEBSITE_SYNC_ENABLED`: `true` to transfer schedules, `false` to pause.

In the website repository:
- Actions secret `CLOUDFLARE_API_TOKEN`: account-scoped Cloudflare Pages Edit token.
- Actions variables `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_PROJECT_NAME`.
- Actions variable `CLOUDFLARE_ENABLED`: `true` to publish, `false` to pause.

Set the Cloudflare token directly in GitHub Settings → Secrets and variables →
Actions. Do not paste secrets into documentation, source, or chat.

## Finish migration after Cloudflare works

1. Complete the new website README's Cloudflare connection steps.
2. Verify the live Cloudflare URL, custom domain, mobile layout, and calendar download.
3. Run **Sync Rally49 website schedule** manually; confirm checks and deployment.
4. Disable the old **Deploy Her Match Website** workflow, then unpublish the old
   Pages site under Settings → Pages. The new site must work before this step.
5. Make this repository private under Settings → General → Danger Zone → Change
   visibility. This affects public access and may affect GitHub Pages depending on
   your GitHub plan. Check Actions remains enabled and its usage allowance.
6. Optional later cleanup: remove legacy frontend files and move the event generator
   and its output to a dedicated data path, updating `sync-website.yml` accordingly.

Do not delete legacy website files before disabling its old deployment workflow.
The private website repository alone does not hide this currently public repository.

## When returning to this project

For a feature: open `rally49-website`, create a feature branch, make changes, run
checks, and merge a PR into main. For schedule problems: open this repository and
inspect the collector workflow first, then sync, then the website deployment.
For credential rotation, rollback, and pause instructions, use the website README.

Ask Codex: "Read docs/WEBSITE_AUTOMATION.md and the website README, check the latest
collector/sync/publish runs, and resume the Cloudflare setup from its current state."
