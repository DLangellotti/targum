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

Video notes. A video reader's folder carries `video/part-NNN.mp4` sidecars — 50–100 MB
per part — so a shipped folder is gigabytes where an audio one was tens of megabytes;
budget the box's disk and the rsync accordingly (`ship-audio.sh` copies whole folders).
Caddy needs no change: chunked uploads stay 8 MiB under the 48 MB body ceiling, and
responses stream, so the reader's Range requests pass through. Hosted video transcodes
on the box at roughly real-time ÷ 4 per part. The box never fetches from YouTube —
that import is CLI-only, on purpose.
