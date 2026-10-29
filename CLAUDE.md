# CLAUDE.md

Auto-publishes **organic** posts for My House Guardian. Finished posts (JPEG + caption + time) go in `queue/<folder>/`, and GitHub Actions publishes them through Meta's Instagram API. See README.md and SETUP.md for how it works today, and docs/RESEARCH.md and docs/PLAN.md for the API research and planned improvements.

## Rules for this project

- **Organic content only.** Never touch ads, boosting, or the Marketing API's ad endpoints. Don't request ad permissions (`ads_management`, `ads_read`) or use ad-related parameters.
- **Ask before adding any new API, library, or outside service.** That includes new Meta APIs (for example the Facebook Pages API), pip/npm packages and third-party hosts.
- **No paid services unless the owner approves.** Everything must stay free to run on GitHub Actions.
- **No hardcoded secrets.** Every secret or key goes in `.env.example` and `SETUP.md` as a fill-in-the-blank, read from environment variables at runtime.
- **Adding a post stays simple:** drop a folder into `queue/` with `post.json` and images. Don't add steps beyond that.

## Conventions

- `poster/` is Python standard library only (no pip installs in the workflows).
- Meta's API changes often. Check the current docs at developers.facebook.com before changing API calls, and cite the page in docs/RESEARCH.md.
- Run `python poster/queue_check.py` after touching `queue/` or `poster/`.
