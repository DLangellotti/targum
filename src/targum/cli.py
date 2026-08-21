"""The targum command line."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table

from . import config as config_module
from . import ingest
from . import segment as segment_module
from . import translate as translate_module
from .cache import Cache
from .errors import TargumError
from .ids import slug
from .models import Style
from .paths import cache_dir, config_path, model_dir
from .pipeline import Build

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Turn a text and its translations into a bilingual HTML reader.",
)
models_app = typer.Typer(no_args_is_help=True, help="Manage language models.")
cache_app = typer.Typer(no_args_is_help=True, help="Manage the cache.")
app.add_typer(models_app, name="models")
app.add_typer(cache_app, name="cache")

console = Console()
err = Console(stderr=True)

# Above this, a run asks before it spends.
CONFIRM_ABOVE_USD = 0.50


def fail(error: TargumError) -> None:
    err.print(f"[red]{error.message}[/red]")
    if error.hint:
        err.print(f"[dim]{error.hint}[/dim]")
    raise typer.Exit(1)


@app.command()
def build(
    # A string, not a Path: pathlib collapses the double slash in https:// and would
    # quietly turn every link into a missing file.
    source: Annotated[
        str, typer.Argument(help="A file, a link, or gutenberg:/wikisource: by name.")
    ],
    to: Annotated[str, typer.Option("--to", help="Target language, as a BCP-47 tag.")] = "en",
    source_language: Annotated[
        str | None,
        typer.Option("--from", help="Source language. Detected from the script if omitted."),
    ] = None,
    style: Annotated[
        Style, typer.Option("--style", help="Idiomatic, or close to the source structure.")
    ] = Style.natural,
    provider: Annotated[str | None, typer.Option("--provider")] = None,
    model: Annotated[str | None, typer.Option("--model", help="Provider model id.")] = None,
    out: Annotated[Path | None, typer.Option("--out", help="Where to write.")] = None,
    translation: Annotated[
        list[Path] | None,
        typer.Option(
            "--translation",
            help="An existing translation to align. Repeat for several.",
        ),
    ] = None,
    machine: Annotated[
        bool | None,
        typer.Option(
            "--machine/--no-machine",
            help="Also machine-translate. On by default only when no --translation is given.",
        ),
    ] = None,
    words: Annotated[
        bool,
        typer.Option(
            "--words",
            help="Make every word tappable, with its dictionary form and difficulty.",
        ),
    ] = False,
    gloss: Annotated[
        bool,
        typer.Option("--gloss", help="Also look up every word. Implies --difficulty."),
    ] = False,
    force: Annotated[bool, typer.Option("--force", help="Redo every stage.")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Do not ask before spending.")] = False,
) -> None:
    """Build a bilingual reader from one text."""
    settings = config_module.load()
    builder = Build(
        source,
        target_language=to,
        source_language=source_language,
        style=style,
        provider_name=provider or settings.provider,
        model=model or settings.model,
        out=out or (Path(settings.out) if settings.out else None),
        force=force,
        batch_size=settings.batch_size,
        effort=settings.effort,
        translations=translation or [],
        machine=machine,
        difficulty=words,
        gloss=gloss,
        notify=lambda message: console.print(f"[dim]{message}[/dim]"),
    )

    try:
        if words or gloss:
            from .annotate import frequency_available
            from .annotate.frequency import MISSING

            if not frequency_available():
                raise TargumError(*MISSING)

        usable, detail = builder.provider.available()
        if builder.machine and not usable:
            raise TargumError(f"Provider '{builder.provider_name}' is not ready.", detail)

        with console.status("Reading and segmenting..."):
            plan = builder.plan()

        count = len(plan.segmented.segments) if plan.segmented else 0
        console.print(
            f"[bold]{plan.document.title or Path(source).name}[/bold] "
            f"[dim]{plan.document.language} → {to}, {count} segments[/dim]"
        )

        if plan.needs_payment:
            console.print(f"[dim]Estimated cost: about ${plan.estimated_cost:.2f}[/dim]")
            if plan.estimated_cost > CONFIRM_ABOVE_USD and not yes:
                if not typer.confirm("Translate?", default=True):
                    raise typer.Abort()

        if plan.cached_translation is not None:
            result = builder.run(plan)
        else:
            with Progress(
                TextColumn("[dim]translating[/dim]"),
                BarColumn(),
                TextColumn("{task.completed}/{task.total}"),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("translate", total=count)
                result = builder.run(plan, lambda done: progress.advance(task, done))
    except TargumError as error:
        fail(error)

    if result.glossary is not None:
        console.print(f"[dim]  {len(result.glossary.entries)} words glossed[/dim]")
    if result.annotation is not None:
        from .annotate import BAND_NAMES, method_label

        annotation = result.annotation
        total = sum(annotation.counts().values())
        if annotation.method == "none":
            console.print(f"[dim]  {total} words tappable, {method_label('none')}[/dim]")
        else:
            spread = ", ".join(
                f"{count} {BAND_NAMES.get(level, level)}"
                for level, count in annotation.counts().items()
            )
            console.print(
                f"[dim]  {total} words tappable, rated "
                f"{method_label(annotation.method)}: {spread}[/dim]"
            )
    for item in result.translations:
        coarse = f", {len(item.coarse)} paragraph-paired" if item.coarse else ""
        console.print(f"[dim]  {item.name} ({item.kind}{coarse})[/dim]")
    if result.reused:
        console.print(f"[dim]Reused: {', '.join(result.reused)}[/dim]")
    pages = len(result.pages) - (0 if len(result.pages) == 1 else 1)
    console.print(
        f"[green]Wrote[/green] {result.index} [dim]({pages} section"
        f"{'' if pages == 1 else 's'})[/dim]"
    )


@app.command()
def fetch(
    source: Annotated[
        str, typer.Argument(help="A file, a link, or gutenberg:/wikisource: by name.")
    ],
    out: Annotated[Path | None, typer.Option("--out", help="Where to write the file.")] = None,
) -> None:
    """Download a public domain text to a markdown file you can edit, then build."""
    try:
        with console.status(f"Fetching {source}..."):
            document = ingest.load(source)
        path = out or Path.cwd() / f"{slug(document.title or source)}.{document.language}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(ingest.to_markdown(document), encoding="utf-8")
    except TargumError as error:
        fail(error)

    words = sum(len(block.text.split()) for block in document.blocks)
    console.print(
        f"[green]Wrote[/green] {path} "
        f"[dim]{document.language}, {len(document.blocks)} blocks, ~{words:,} words[/dim]"
    )
    console.print(f"[dim]targum build {path} --to en[/dim]")


@app.command(name="gloss")
def gloss_command(
    source: Annotated[str, typer.Argument(help="The text to look words up in: a file or a link.")],
    to: Annotated[str, typer.Option("--to", help="Language to gloss into.")] = "en",
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Count the words and the cost, spend nothing.")
    ] = False,
    from_level: Annotated[
        int,
        typer.Option(
            "--from-level",
            min=1,
            max=6,
            help="Only look up words this rare or rarer: 1 everyday, 6 rare.",
        ),
    ] = 1,
    out: Annotated[Path | None, typer.Option("--out", help="Where to write the glossary.")] = None,
) -> None:
    """Look up every word in a text, and cache the results across every text."""
    from .annotate import BAND_NAMES, Annotator, frequency_available
    from .annotate.frequency import MISSING
    from .annotate.gloss import AnthropicGlosses, build_glossary, estimate, unique_lemmas
    from .segment import StanzaSegmenter, segment_document

    try:
        if not frequency_available():
            raise TargumError(*MISSING)
        with console.status("Reading, segmenting and lemmatizing..."):
            document = ingest.load(source)
            segmented = segment_document(document, StanzaSegmenter())
            annotation = Annotator().annotate(segmented)

        lemmas = unique_lemmas(annotation, min_band=from_level)
        provider = AnthropicGlosses()
        tokens = sum(len(items) for items in annotation.tokens.values())
        cost = estimate(len(lemmas), provider.model)

        console.print(
            f"[bold]{document.title or Path(source).name}[/bold] "
            f"[dim]{tokens} words, {len(lemmas)} distinct dictionary forms"
            f"{f' rated {BAND_NAMES[from_level]} or rarer' if from_level > 1 else ''}[/dim]"
        )
        console.print(f"[dim]Glossing all of them would cost about ${cost:.2f} at most.[/dim]")
        console.print("[dim]Anything already glossed in this language pair is free.[/dim]")
        if dry_run:
            return

        usable, detail = provider.available()
        if not usable:
            raise TargumError("The Anthropic provider is not ready.", detail)
        if cost > CONFIRM_ABOVE_USD and not typer.confirm("Look them up?", default=True):
            raise typer.Abort()

        with Progress(
            TextColumn("[dim]glossing[/dim]"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("gloss", total=len(lemmas))
            glossary, paid = build_glossary(
                annotation,
                to,
                provider,
                min_band=from_level,
                on_progress=lambda n: progress.advance(task, n),
            )
    except TargumError as error:
        fail(error)

    path = out or Path.cwd() / f"{slug(Path(source).stem)}.{to}.glossary.json"
    glossary.write(path)
    console.print(
        f"[green]Wrote[/green] {path} "
        f"[dim]{len(glossary.entries)} glossed, {len(lemmas) - paid} already cached[/dim]"
    )


@app.command()
def align(
    source: Annotated[Path, typer.Argument(help="The original text.")],
    translation: Annotated[Path, typer.Argument(help="An existing translation of it.")],
    out: Annotated[Path | None, typer.Option("--out", help="Where to write the alignment.")] = None,
) -> None:
    """Align an existing translation to a source, and report how well it went."""
    from . import align as align_module
    from .segment import StanzaSegmenter, segment_document

    try:
        segmenter = StanzaSegmenter()
        with console.status("Reading and segmenting..."):
            source_document = ingest.load(str(source))
            target_document = ingest.load(str(translation))
            segmented = segment_document(source_document, segmenter)
            target = segment_document(target_document, segmenter)

        with console.status("Aligning..."):
            alignment = align_module.align(
                segmented, target, target_document.title or translation.stem
            )
    except TargumError as error:
        fail(error)

    path = out or Path.cwd() / f"{slug(source.stem)}.{target.language}.alignment.json"
    alignment.write(path)

    shapes: dict[str, int] = {}
    for link in alignment.links:
        shapes[link.kind] = shapes.get(link.kind, 0) + 1
    coarse = sum(1 for link in alignment.links if link.coarse)
    confident = sum(1 for link in alignment.links if link.confidence >= 0.5)

    console.print(
        f"[bold]{segmented.language} → {target.language}[/bold] "
        f"[dim]{len(segmented.segments)} against {len(target.segments)} segments[/dim]"
    )
    console.print(
        f"[dim]{len(alignment.links)} links: "
        f"{', '.join(f'{count}×{shape}' for shape, count in sorted(shapes.items()))}[/dim]"
    )
    console.print(
        f"[dim]{confident} confident, {coarse} collapsed to paragraphs, "
        f"length ratio {alignment.length_ratio}[/dim]"
    )
    console.print(f"[green]Wrote[/green] {path}")


@app.command()
def serve(
    port: Annotated[int, typer.Option("--port", help="Port to listen on.")] = 8420,
    out: Annotated[Path | None, typer.Option("--out", help="Where readers are kept.")] = None,
    open_browser: Annotated[
        bool, typer.Option("--open/--no-open", help="Open the page automatically.")
    ] = True,
    max_cost: Annotated[
        float, typer.Option("--max-cost", help="Most one text may cost, in dollars.")
    ] = 2.00,
    budget: Annotated[
        float, typer.Option("--budget", help="Most this session may spend, in dollars.")
    ] = 10.00,
) -> None:
    """Open a page for building readers, without the terminal."""
    from .serve import start

    directory = out or Path.cwd() / "targum-out"
    directory.mkdir(parents=True, exist_ok=True)
    console.print(f"[dim]Readers are kept in {directory}[/dim]")

    def announce(address: str) -> None:
        # The key is part of the address, so it has to be printed with it.
        console.print(f"[green]targum[/green] is at [bold]{address}[/bold]")
        console.print("[dim]Only this machine can reach it. Ctrl-C to stop.[/dim]")

    console.print(
        f"[dim]Spending is capped at ${max_cost:.2f} for one text and "
        f"${budget:.2f} for this session.[/dim]"
    )
    start(
        directory,
        port=port,
        open_browser=open_browser,
        max_cost=max_cost,
        budget=budget,
        announce=announce,
    )
    console.print("[dim]Stopped.[/dim]")


@app.command()
def sources() -> None:
    """List everything targum can read."""
    for name in ingest.sources():
        console.print(f"  {name}")
    console.print("[dim]PDF is not supported.[/dim]")


@app.command()
def providers() -> None:
    """List translation providers and whether they can be used right now."""
    table = Table(box=None, pad_edge=False)
    table.add_column("provider")
    table.add_column("ready")
    table.add_column("")
    for name in translate_module.names():
        instance = translate_module.build(name)
        usable, detail = instance.available()
        table.add_row(name, "[green]yes[/green]" if usable else "[yellow]no[/yellow]", detail)
    console.print(table)
    console.print(f"[dim]Config: {config_path()}[/dim]")


@models_app.command("list")
def models_list() -> None:
    """Show downloaded language models."""
    from .align import embedding

    for name in embedding.downloaded_models():
        console.print(f"  {name}  [dim]{embedding.model_size(name) / 1_000_000:.0f} MB[/dim]")

    languages = segment_module.downloaded_languages()
    if not languages and not embedding.downloaded_models():
        console.print("[dim]No language models downloaded yet.[/dim]")
        console.print("[dim]They download on first use, or run: targum models fetch he[/dim]")
        return
    for language in languages:
        size = sum(f.stat().st_size for f in (model_dir() / language).rglob("*") if f.is_file())
        console.print(f"  {language}  [dim]{size / 1_000_000:.0f} MB[/dim]")
    console.print(f"[dim]{model_dir()}[/dim]")


@models_app.command("fetch")
def models_fetch(
    language: Annotated[str, typer.Argument(help="A language tag, such as he or ru.")],
) -> None:
    """Download a language model ahead of time. Use 'embeddings' for the aligner."""
    from .align import embedding

    if language in {"embeddings", "align", "aligner"}:
        if embedding.is_downloaded():
            console.print("[dim]The embedding model is already downloaded.[/dim]")
            return
        console.print(f"[dim]Fetching {embedding.DEFAULT_MODEL}, about 1.8 GB...[/dim]")
        try:
            embedding.SentenceTransformerEncoder().encoder()
        except TargumError as error:
            fail(error)
        console.print(f"[green]Downloaded[/green] {embedding.DEFAULT_MODEL}")
        return

    code = segment_module.stanza_code(language)
    from .annotate.lemma import PROCESSORS

    if segment_module.has_processors(code, PROCESSORS):
        console.print(f"[dim]{code} is already downloaded.[/dim]")
        return
    try:
        segment_module.download(code, processors=PROCESSORS)
    except TargumError as error:
        fail(error)
    console.print(f"[green]Downloaded[/green] {code}")


@models_app.command("remove")
def models_remove(language: Annotated[str, typer.Argument()]) -> None:
    """Delete a downloaded language model."""
    code = segment_module.stanza_code(language)
    if segment_module.remove(code):
        console.print(f"[green]Removed[/green] {code}")
    else:
        console.print(f"[dim]{code} was not downloaded.[/dim]")


@cache_app.command("clear")
def cache_clear() -> None:
    """Drop cached translations. Language models are kept."""
    removed = Cache().clear()
    console.print(f"[green]Cleared[/green] {removed} cached items [dim]{cache_dir()}[/dim]")


def main() -> None:
    try:
        app()
    except KeyboardInterrupt:
        err.print("[dim]Stopped. Finished work is cached.[/dim]")
        sys.exit(130)


if __name__ == "__main__":
    main()
