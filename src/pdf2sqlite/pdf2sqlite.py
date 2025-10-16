import os
import io
import argparse
import sqlite3
from dataclasses import dataclass, field
from argparse import Namespace
from sqlite3 import Connection, Cursor

from PIL import Image
from pypdf import PdfReader, PdfWriter, PageObject
import pypdf.filters
from rich.live import Live
from rich_argparse import RichHelpFormatter
from gmft.formatters.base import FormattedTable

from .validation import validate_args
from .summarize import summarize
from .abstract import abstract
from .extract_sections import extract_toc_and_sections
from .init_db import init_db
from .pdf_to_table import get_rich_tables
from .embeddings import process_pdf_for_semantic_search
from .describe_figure import describe
from .view import fresh_view
from .task_stack import TaskStack

def nerd_icon(glyph: str) -> str:
    return f"{glyph} " if os.getenv("NERD_FONT") else ""

@dataclass
class PdfContext:
    args: Namespace
    cursor: Cursor
    live: Live
    title: str
    length: int
    description: str | None = None
    pdf_id: int | None = None
    gists: list[str] = field(default_factory=list)
    rich_tables: list[FormattedTable] | None = None
    tasks: TaskStack = field(init=False)

    def __post_init__(self) -> None:
        self.tasks = TaskStack(self.live, self.title)


@dataclass
class PageContext:
    pdf: PdfContext
    page: PageObject
    page_number: int
    page_bytes: bytes
    page_id: int
    fresh_page: bool
    existing_row: tuple[int, str | None] | None


def generate_description(reader: PdfReader, context: PdfContext) -> str:
    new_pdf = PdfWriter(None)
    pages = reader.pages[:10]
    for index, page in enumerate(pages):
        new_pdf.insert_page(page, index)
    pdf_bytes = io.BytesIO()
    new_pdf.write(pdf_bytes)
    with context.tasks.step("Generating PDF description"):
        return abstract(
            context.title,
            pdf_bytes.getvalue(),
            context.args.abstracter,
            context.tasks,
        )


def insert_pdf_by_name(title: str, description: str | None, cursor: Cursor) -> int:
    cursor.execute("SELECT id FROM pdfs WHERE title = ?", [title])
    row: tuple[int] | None = cursor.fetchone()

    if row is None:
        cursor.execute(
            "INSERT INTO pdfs (title, description) VALUES (?,?)",
            [title, description],
        )
        if cursor.lastrowid is None:
            raise Exception(
                "Something went wrong while attempting to insert the pdf "
                f"'{title} in the database"
            )
        return cursor.lastrowid
    return row[0]


def insert_sections(sections, context: PdfContext) -> None:
    if context.pdf_id is None:
        raise ValueError("PDF identifier is not available")
    for _, section in sections.items():
        if section["title"] and section["start_page"]:
            title = section["title"]
            start_page = section["start_page"]
            context.cursor.execute(
                "SELECT * FROM pdf_sections WHERE title = ? AND pdf_id = ?",
                [title, context.pdf_id],
            )
            if context.cursor.fetchone() is None:
                context.cursor.execute(
                    "INSERT INTO pdf_sections (start_page, title, pdf_id) "
                    "VALUES (?,?,?)",
                    [start_page, title, context.pdf_id],
                )
                section_id = context.cursor.lastrowid
                context.cursor.execute(
                    "INSERT INTO pdf_to_section (pdf_id, section_id) VALUES (?,?)",
                    [context.pdf_id, section_id],
                )


def extract_figures(page_ctx: PageContext) -> None:
    context = page_ctx.pdf
    args = context.args
    cursor = context.cursor
    live = context.live

    if page_ctx.fresh_page:
        try:
            images = list(page_ctx.page.images)
            total = len(images)
            if total:
                with context.tasks.step("extracting figures"):
                    for index, fig in enumerate(images, start=1):
                        label = f"extracting figure {index}/{total}"
                        with context.tasks.step(label):
                            image = getattr(fig, "image", None)
                            if image is None:
                                continue
                            height = getattr(image, "height", None)
                            width = getattr(image, "width", None)
                            if height is None or width is None:
                                continue
                            if min(height, width) < args.lower_pixel_bound:
                                # we skip small image smaller than a certain
                                # bound, which are often icons, watermarks,
                                # etc.
                                continue
                            mime_type = Image.MIME.get(image.format.upper())
                            if mime_type:
                                context.tasks.update_current(f"{label}, {mime_type}")
                            try:
                                cursor.execute(
                                    "INSERT INTO pdf_figures (data, description, mime_type) "
                                    "VALUES (?,?,?)",
                                    [fig.data, None, mime_type],
                                )
                                figure_id = cursor.lastrowid
                                cursor.execute(
                                    "INSERT INTO page_to_figure (page_id, figure_id) VALUES (?,?)",
                                    [page_ctx.page_id, figure_id],
                                )
                            except Exception as exc:
                                live.console.print(
                                    f"[red]extract {mime_type} on p{page_ctx.page_number} failed: {exc}"
                                )
        except Exception as exc:
            live.console.print(
                f"[red] extracting images for p{page_ctx.page_number} failed: {exc}"
            )

    if args.vision_model:
        cursor.execute(
            """
            SELECT pdf_figures.description,
                   pdf_figures.id,
                   pdf_figures.data,
                   pdf_figures.mime_type
            FROM pdf_figures
            JOIN page_to_figure ON pdf_figures.id = page_to_figure.figure_id
            JOIN pdf_pages ON page_to_figure.page_id = pdf_pages.id
            WHERE pdf_pages.id = ?
            """,
            [page_ctx.page_id],
        )
        figures = cursor.fetchall()
        total = len(figures)
        if total:
            describe_label = f"{nerd_icon('')}describing figures"
            with context.tasks.step(describe_label):
                for index, fig in enumerate(figures, start=1):
                    figure_label = f"describing figure {index}/{total}"
                    with context.tasks.step(figure_label):
                        if fig[0] is None:
                            if fig[3]:
                                context.tasks.update_current(
                                    f"{figure_label}, {fig[3]}"
                                )
                            try:
                                fig_description = describe(
                                    fig[2],
                                    fig[3],
                                    args.vision_model,
                                    context.tasks,
                                )
                                cursor.execute(
                                    "UPDATE pdf_figures SET description = ? WHERE id = ?",
                                    [fig_description, fig[1]],
                                )
                            except Exception as exc:
                                live.console.print(
                                    f"[red]describe {fig[3]} on p{page_ctx.page_number} failed: {exc}"
                                )


def summarize_pages(page_ctx: PageContext) -> None:
    context = page_ctx.pdf
    row = page_ctx.existing_row
    args = context.args
    if (row is None or row[1] is None) and args.summarizer:
        with context.tasks.step("adding page summaries"):
            gist = summarize(
                context.gists,
                context.description,
                page_ctx.page_number,
                context.title,
                page_ctx.page_bytes,
                args.summarizer,
                context.tasks,
            )
            context.gists.append(gist)
            if len(context.gists) > 5:
                context.gists.pop(0)
            context.cursor.execute(
                "UPDATE pdf_pages SET gist = ? WHERE id = ?",
                [gist, page_ctx.page_id],
            )


def insert_tables(page_ctx: PageContext) -> None:
    context = page_ctx.pdf
    args = context.args
    if not args.tables or context.rich_tables is None:
        return

    tables = context.rich_tables
    page_number = page_ctx.page_number
    indexed_tables = [
        (index, table)
        for index, table in enumerate(tables, start=1)
        if table.page.page_number + 1 == page_number
    ]

    if not indexed_tables:
        return

    with context.tasks.step("inserting tables"):
        total = len(tables)
        for index, table in indexed_tables:
            table_label = f"inserting table: {index}/{total}"
            with context.tasks.step(table_label):
                buffered = io.BytesIO()
                table.image().save(buffered, format="JPEG")
                image_bytes = buffered.getvalue()
                try:
                    text = table.df().to_markdown()
                    if args.vision_model:
                        describe_label = f"{nerd_icon('')}describing table"
                        with context.tasks.step(describe_label):
                            table_description = describe(
                                image_bytes,
                                "image/jpg",
                                args.vision_model,
                                context.tasks,
                            )
                    else:
                        table_description = None
                    context.cursor.execute(
                        "INSERT INTO pdf_tables (text, image, description, caption_above, "
                        "caption_below, pdf_id, page_number, xmin, ymin) VALUES (?,?,?,?,?,?,?,?,?)",
                        [
                            text,
                            image_bytes,
                            table_description,
                            table.captions()[0],
                            table.captions()[1],
                            context.pdf_id,
                            page_number,
                            table.bbox[0],
                            table.bbox[1],
                        ],
                    )
                    table_id = context.cursor.lastrowid
                    context.cursor.execute(
                        "INSERT INTO page_to_table (page_id, table_id) VALUES (?,?)",
                        [page_ctx.page_id, table_id],
                    )
                except Exception as exc:
                    context.live.console.print(
                        f"[red]extract table on p{page_number} failed: {exc}"
                    )


def process_page(page: PageObject, context: PdfContext) -> None:
    if context.pdf_id is None:
        raise ValueError("PDF identifier is not available")

    page_number = (page.page_number or 0) + 1
    with context.tasks.step(f"extracting page {page_number}/{context.length}"):
        context.cursor.execute(
            "SELECT id, gist FROM pdf_pages WHERE pdf_id = ? AND page_number = ?",
            [context.pdf_id, page_number],
        )
        row = context.cursor.fetchone()
        new_pdf = PdfWriter(None)
        new_pdf.insert_page(page)
        pdf_bytes = io.BytesIO()
        new_pdf.write(pdf_bytes)
        page_bytes = pdf_bytes.getvalue()

        if row is None:
            fresh_page = True
            with context.tasks.step("extracting text"):
                context.cursor.execute(
                    "INSERT INTO pdf_pages (page_number, data, text, pdf_id) VALUES (?,?,?,?)",
                    [page_number, page_bytes, page.extract_text(), context.pdf_id],
                )
            page_id = context.cursor.lastrowid
            if page_id is None:
                raise Exception(
                    "Something went wrong while inserting page "
                    f"{page_number} into {context.title}"
                )
            context.cursor.execute(
                "INSERT INTO pdf_to_page (pdf_id, page_id) VALUES (?,?)",
                [context.pdf_id, page_id],
            )
        else:
            fresh_page = False
            page_id = row[0]

        page_ctx = PageContext(
            pdf=context,
            page=page,
            page_number=page_number,
            page_bytes=page_bytes,
            page_id=page_id,
            fresh_page=fresh_page,
            existing_row=row,
        )

        extract_figures(page_ctx)
        summarize_pages(page_ctx)
        insert_tables(page_ctx)


def insert_pdf(args: Namespace,
               the_pdf: str,
               live: Live,
               cursor: Cursor,
               db: Connection) -> None:
    reader = PdfReader(the_pdf)
    title = (
        reader.metadata.title
        if reader.metadata and reader.metadata.title
        else os.path.basename(the_pdf)
    )

    context = PdfContext(args=args, cursor=cursor, live=live, title=title, length=len(reader.pages))

    if args.abstracter:
        context.description = generate_description(reader, context)

    context.pdf_id = insert_pdf_by_name(title, context.description, cursor)
    db.commit()

    toc_and_sections = extract_toc_and_sections(reader, live)

    if toc_and_sections["sections"]:
        insert_sections(toc_and_sections["sections"], context)

    db.commit()

    if args.embedder:
        process_pdf_for_semantic_search(
            toc_and_sections,
            cursor,
            context.pdf_id,
            args.embedder,
        )

    db.commit()

    if args.tables:
        with context.tasks.step(f"{nerd_icon('')}Processing rich tables"):
            context.rich_tables = get_rich_tables(the_pdf)
    else:
        context.rich_tables = None

    for page in reader.pages:
        process_page(page, context)
        db.commit()



def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pdf2sqlite",
        description="Convert PDFs into an easy-to-query SQLite DB",
        formatter_class=RichHelpFormatter,
    )

    def nonnegative_int(value: str) -> int:
        ival = int(value)
        if ival < 0:
            raise argparse.ArgumentTypeError(
                "the supplied bound must be a non-negative integer, got "
                f"'{value}'"
            )
        return ival

    parser.add_argument("-p", "--pdfs",
                        help = "PDFs to add to DB", nargs="+", required= True)
    parser.add_argument("-d", "--database",
                        help = "Database where PDF will be added", required= True)
    parser.add_argument("-s", "--summarizer",
                        help = "An LLM to sumarize PDF pages (litellm naming conventions)")
    parser.add_argument("-a", "--abstracter",
                        help = "An LLM to produce an abstract (litellm naming conventions)")
    parser.add_argument("-e", "--embedder",
                        help = "An embedding model to generate vector embeddings (litellm naming conventions)")
    parser.add_argument("-v", "--vision_model",
                        help = "A vision model to describe images (litellm naming conventions)")
    parser.add_argument("-t", "--tables", action = "store_true",
                        help = "Use gmft to analyze tables (will also use a vision model if available)")
    parser.add_argument("-o", "--offline", action = "store_true",
                        help = "Offline mode for gmft (blocks hugging face telemetry, solves VPN issues)")
    parser.add_argument("-l", "--lower_pixel_bound", type=nonnegative_int, default=100,
                        help = "Lower bound on pixel size for images")
    parser.add_argument("-z", "--decompression_limit", type=nonnegative_int,
                        help = "Upper bound on size for decompressed images. default 75,000,000. zero disables")
    args = parser.parse_args()

    if args.offline:
        os.environ["HF_HUB_OFFLINE"] = "1"

    if args.decompression_limit:
        pypdf.filters.ZLIB_MAX_OUTPUT_LENGTH = args.decompression_limit

    validate_args(args)

    with Live(fresh_view(), refresh_per_second=4) as live:
        try:
            update_db(args, live)
        except KeyboardInterrupt:
            live.console.print("Cancelled, shutting down")


def update_db(args: Namespace, live: Live) -> None:
    db = sqlite3.connect(args.database)

    # check if pdf_pages table exists
    cursor = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='pdf_pages'"
    )

    rows = cursor.fetchall()

    if len(rows) < 1:
        live.console.print(f"[blue]{"󰪩 " if os.getenv("NERD_FONT") else ""}Initializing new database")
        init_db(cursor)

    for pdf in args.pdfs:
        insert_pdf(args, pdf, live, cursor, db)
