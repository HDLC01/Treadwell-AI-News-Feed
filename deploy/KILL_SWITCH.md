# Kill switch — Treadwell News Feed

Emergency commands on the VPS (ssh -i ~/.ssh/treadwell_vps root@50.6.110.215),
installed at /usr/local/bin (mirrors the proposal tool's tw-*):

| Command     | Effect |
|-------------|--------|
| `nf-down`   | Stops the container — newsfeed.wetreadwell.com goes OFFLINE instantly |
| `nf-up`     | Brings it back online (~10s to healthy) |
| `nf-status` | Shows container state + /api/health code |

To (re)install on the VPS, copy these scripts to /usr/local/bin and `chmod +x`.
