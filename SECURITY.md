# Security

targum is a local tool. Everything it builds is a static HTML file, and the one
network-facing piece, `targum serve`, is deliberately not a hosted service:

- It binds to 127.0.0.1 only.
- Every request needs a key generated at startup and printed once; comparisons are
  constant-time.
- Requests whose Host header is not a loopback name are refused, which blocks DNS
  rebinding.
- Uploads are capped at 32 MB, restricted to the file types targum reads, and named
  by basename only.
- Files are served only from inside the output directory, after path resolution.
- Rendered pages are built with autoescaping on, and text from fetched web pages is
  escaped before it reaches a reader.

What it does not defend against, by design: anything with the key has full use of
the builder, including spending against the configured budget caps, and the key
travels in the URL. Do not put `targum serve` behind a reverse proxy on a public
host; the pipeline is separable from the server precisely so a hosted version can
replace this layer.

To report a vulnerability, open a GitHub issue. If it is sensitive, say so in the
issue without details and a private channel will be arranged.
