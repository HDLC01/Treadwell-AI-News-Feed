# Kill switch — Treadwell News Feed

Emergency commands on the VPS (`ssh treadwell-vps`), installed at /usr/local/bin
(mirrors the proposal tool's tw-*). The alias logs in as `hanztwell`; the box runs
every command as root via sudo, e.g. `ssh treadwell-vps nf-down`.

| Command     | Effect |
|-------------|--------|
| `nf-down`   | Stops the container — newsfeed.wetreadwell.com goes OFFLINE instantly |
| `nf-up`     | Brings it back online (~10s to healthy) |
| `nf-status` | Shows container state + /api/health code |

To (re)install on the VPS, copy these scripts to /usr/local/bin and `chmod +x`.
