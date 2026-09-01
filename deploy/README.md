# deploy

targum behind Caddy on one box. Loopback only; Caddy terminates TLS.

Once, as root on a fresh Debian or Ubuntu box:

```
scp -r deploy root@box:/tmp/ && ssh root@box bash /tmp/deploy/provision.sh
```

Then fill in `/etc/targum/targum.env` and point the A record at the box.

Every time after that, from here:

```
TARGUM_HOST=root@targum.page ./deploy/deploy.sh
```

It runs the checks, builds a wheel, installs it, restarts, and fails loudly if
`/health` does not come back. `targum preflight` is the same gate on the box, and
systemd runs it before every start.

Secrets live in `/etc/targum/targum.env` and nowhere else.

Daily learning is not indexed until `TARGUM_INDEX_DAILY=1` is set on the box, and that
is a separate switch from `TARGUM_INDEX_PARASHA`. Sharing one would mean that inviting
crawlers to fifty-four portions — a corpus that is finished, and the same fifty-four every
year — also invited them to four pages that change every night.

Daily learning. `ship-daily.sh` carries the rolling window of `/mishna-yomi` and its
three siblings. Unlike `ship-parasha.sh` it wants running **nightly**, and that is the
whole difference between them: the parasha's corpus is the same fifty-four readings every
year and shipping it moves a pointer, while a learning cycle is two thousand days of which
fourteen are built. A box a month stale serves a page headed "today" over the wrong
reading. Build first (`targum daily build`), then ship; both are free and neither fetches
a text.

Video notes. A video reader's folder carries `video/part-NNN.mp4` sidecars — 50–100 MB
per part — so a shipped folder is gigabytes where an audio one was tens of megabytes;
budget the box's disk and the rsync accordingly (`ship-audio.sh` copies whole folders).
Caddy needs no change: chunked uploads stay 8 MiB under the 48 MB body ceiling, and
responses stream, so the reader's Range requests pass through. Hosted video transcodes
on the box at roughly real-time ÷ 4 per part. The box never fetches from YouTube —
that import is CLI-only, on purpose.
