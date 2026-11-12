# the films

A few seconds of a real video that a public page plays, muted, with its words lit as
they are said. Served from targum's own origin by a hash address (`builder._films`), in
ranges (`serve._asset_file`), and kept for a year, as the pictures are. Nothing is
fetched from anybody else's origin (design.md §12, 2026-10-30).

| file | what | source | licence |
|---|---|---|---|
| `kan-small-cola.mp4` | Seconds 15.3 to 20.2 of "Why does a small cola cost more than a big one?" (catalogue `kan-small-cola`), on /after-duolingo-hebrew's "People talk fast" | [כאן מסבירים](https://www.youtube.com/watch?v=NEoaePzDhGc), כאן \| דיגיטל - תאגיד השידור הישראלי | **CC BY 3.0** |

Cut on 2026-11-12 from the part targum's own build keeps, with no sound (the page plays it
muted) and small enough to ride beside the page: 640×360, H.264, CRF 30, 4.9 seconds,
113 kB.

    ffmpeg -ss 15.3 -to 20.2 -i part-001.mp4 -an -vf scale=640:-2 -c:v libx264 \
      -preset slow -crf 30 -pix_fmt yuv420p -profile:v high -movflags +faststart \
      kan-small-cola.mp4

The page credits it under the picture, with the link and the licence, because a credit
that lives only in a repository is a credit nobody reading the page ever sees. Its words'
clocks are in `render/after_duolingo_clip.json`.
