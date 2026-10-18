#!/usr/bin/env bash
# Sunday's triage, read off the site's own database (targum-internal#459).
#
#   TARGUM_HOST=root@targum.page ./deploy/triage.sh > triage.md
#
# The Tell us messages and the browser faults live on the box, so a triage from the
# laptop's database finds none of them. This runs `targum triage` there, read-only, and
# prints the week as Markdown: each message and each fault with a draft beta-found card.
# Nothing is filed; the drafts are commands to finish and run by hand.
set -euo pipefail
HOST="${TARGUM_HOST:?set TARGUM_HOST=user@box}"
ssh "$HOST" "sudo -u targum /usr/local/bin/targum triage --store /var/lib/targum/targum.db ${*:-}"
