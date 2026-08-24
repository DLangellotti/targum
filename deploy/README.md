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
