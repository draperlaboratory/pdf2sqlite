import os
import io
import base64
import sys
import sqlite3
from sqlite3 import Connection, Cursor
from PIL import Image
from pypdf import PdfReader, PdfWriter, PageObject
from rich.live import Live
import argparse
from gmft.formatters.base import FormattedTable
from argparse import Namespace
from .summarize import summarize
from .abstract import abstract
from .extract_sections import extract_toc_and_sections
from .init_db import init_db
from .pdf_to_table import get_rich_tables
from .embeddings import process_pdf_for_semantic_search
from .describe_figure import describe
from .view import task_view, fresh_view

def generate_description(title : str, args : Namespace, reader : PdfReader):
    new_pdf = PdfWriter(None)
    pages = reader.pages[:10]
    for i, page in enumerate(pages):
        new_pdf.insert_page(page, i)
    pdf_bytes = io.BytesIO()
    new_pdf.write(pdf_bytes)
    pdf_bytes = pdf_bytes.getvalue()
    description = abstract(title, pdf_bytes, args.abstracter)
    print(f"generated description of PDF: \"{description}\"")
    return description

def insert_pdf_by_name(title : str, description : str | None, cursor : Cursor):
    cursor.execute("SELECT id FROM pdfs WHERE title = ?", [title])
    row : tuple[int] | None = cursor.fetchone()

    if row is None:
        cursor.execute("INSERT INTO pdfs (title, description) VALUES (?,?)", 
                       [title, description])
        if cursor.lastrowid is None:
            raise Exception(f"Something went wrong while attempting to insert the pdf '{title} in the database")
        return cursor.lastrowid
    else:
        return row[0]

def insert_sections(sections, pdf_id : int, cursor : Cursor):
        for _, section in sections.items():
            if section["title"] and section["start_page"]:
                title = section["title"]
                start_page = section["start_page"]
                cursor.execute("SELECT * FROM pdf_sections WHERE title = ? AND pdf_id = ?", [title, pdf_id])
                if cursor.fetchone() is None:
                    cursor.execute(
                            "INSERT INTO pdf_sections (start_page, title, pdf_id) VALUES (?,?,?)", 
                            [start_page, title, pdf_id])
                    section_id = cursor.lastrowid
                    cursor.execute("INSERT INTO pdf_to_section (pdf_id, section_id) VALUES (?,?)",
                           [pdf_id, section_id])

def extract_figures(cursor: Cursor, live : Live, page_number : int, title : str, page, page_id: int, args : Namespace, fresh_page : bool):

    if fresh_page:
        live.update(task_view(title, [f"extracting page {page_number}", "extracting figures"]))
        total = len(page.images)
        try:
            for index, fig in enumerate(page.images):
                # we skip small image smaller than a certain bound, which are often
                # icons, watermarks, etc.
                if min(fig.image.height, fig.image.width) < args.lower_pixel_bound:
                    continue
                mime_type = Image.MIME.get(fig.image.format.upper())
                try:
                    live.update(task_view(title, 
                        ["extracting page", "extracting figures", f"extracting figure {index+1}/{total}, {mime_type}"]))
                    cursor.execute("INSERT INTO pdf_figures (data, description, mime_type) VALUES (?,?,?)", 
                                   [fig.data, None, mime_type])
                    figure_id = cursor.lastrowid
                    cursor.execute("INSERT INTO page_to_figure (page_id, figure_id) VALUES (?,?)",
                                   [page_id, figure_id])

                except Exception as e:
                    live.console.print(f"[red]extract {mime_type} on p{page_number} failed: {e}")
        except Exception as e:
            live.console.print(f"[red] extracting images for p{page_number} failed: {e}")


    if args.vision_model:
        cursor.execute('''
            SELECT pdf_figures.description, pdf_figures.id, pdf_figures.data, pdf_figures.mime_type FROM 
                pdf_figures JOIN page_to_figure ON pdf_figures.id = page_to_figure.figure_id
                            JOIN pdf_pages ON page_to_figure.page_id = pdf_pages.id
            WHERE
                pdf_pages.id = ?

        ''', [page_id])
        figures = cursor.fetchall()
        total = len(figures)
        for index, fig in enumerate(figures):
            try:
                tasks = [f"extracting page {page_number}", f"{" " if os.getenv("NERD_FONT") else ""}describing figures", f"describing figure {index+1}/{total}"]
                if fig[0] is None:
                    fig_description = describe(fig[2], fig[3], args.vision_model, live, page_number, title, tasks)
                    cursor.execute("UPDATE pdf_figures SET description = ? WHERE id = ?",
                                   [fig_description, fig[1]])
            except Exception as e:
                    live.console.print(f"[red]describe {fig[3]} on p{page_number} failed: {e}")

def summarize_pages(row, gists, description : str | None, args : Namespace, cursor: Cursor, live : Live, page_number : int, title : str, pdf_bytes : bytes, page_id : int):
    if (row is None or row[1] is None) and args.summarizer:
        gist = summarize(gists,
                         description,
                         page_number,
                         title,
                         pdf_bytes, 
                         args.summarizer)
        gists.append(gist)
        if (len(gists) > 5):
            gists.pop(0)
        cursor.execute("UPDATE pdf_pages SET gist = ? WHERE id = ?", [gist, page_id])
        live.update(task_view(title, 
             [f"extracting page {page_number}", "adding page summaries", f"inserting gist: {gist}"]))

def insert_tables(page_number : int, title : str, args : Namespace , live : Live, rich_tables, cursor : Cursor, page_id : int, pdf_id : int):
    if args.tables:
        live.update(task_view(title, 
             [f"extracting page {page_number}", "inserting tables"]))
        total = len(rich_tables)
        for index, table in enumerate(rich_tables):
            if table.page.page_number + 1 == page_number:
                tasks = [f"extracting page {page_number}", "inserting tables", f"inserting table: {index+1}/{total}"]
                buffered = io.BytesIO()
                table.image().save(buffered, format="JPEG")
                image_b64 = base64.b64encode(buffered.getvalue())
                try:
                    live.update(task_view(title, tasks))
                    text = table.df().to_markdown()
                    if args.vision_model:
                        tasks = [f"extracting page {page_number}", "inserting tables", f"inserting table: {index+1}/{total}", f"{" " if os.getenv("NERD_FONT") else ""}describing table"]
                        table_description = describe(buffered.getvalue(), "image/jpg", args.vision_model, live, page_number, title, tasks)
                    else:
                        table_description = None
                    cursor.execute(
                            "INSERT INTO pdf_tables (text, image, description, caption_above, caption_below, pdf_id, page_number, xmin, ymin) VALUES (?,?,?,?,?,?,?,?,?)",
                            [text, image_b64, table_description, table.captions()[0], table.captions()[1], pdf_id, page_number, table.bbox[0], table.bbox[1]])
                    table_id = cursor.lastrowid
                    cursor.execute(
                            "INSERT INTO page_to_table (page_id, table_id) VALUES (?,?)",
                            [page_id, table_id])
                except Exception as e:
                    live.console.print(f"[red]extract table on p{page_number} failed: {e}")

def insert_page(page : PageObject,
                rich_tables : list[FormattedTable] | None,
                live : Live,
                pdf_id : int,
                cursor : Cursor,
                args : Namespace,
                gists : list[str],
                title : str,
                description : str | None):

    page_number = (page.page_number or 0) + 1 #pages are zero indexed. We do this to match the probable ToC one-indexing of pages.
    live.update(task_view(title, [f"extracting page {page_number}"]))

    cursor.execute("SELECT id, gist FROM pdf_pages WHERE pdf_id = ? AND page_number = ?", [pdf_id, page_number])
    row = cursor.fetchone()
    new_pdf = PdfWriter(None)
    new_pdf.insert_page(page)
    pdf_bytes = io.BytesIO()
    new_pdf.write(pdf_bytes)
    pdf_bytes = pdf_bytes.getvalue()

    if row is None:
        fresh_page = True
        live.update(task_view(title, [f"extracting page {page_number}", "extracting text"]))
        cursor.execute(
                "INSERT INTO pdf_pages (page_number, data, text, pdf_id) VALUES (?,?,?,?)",
                [page_number, pdf_bytes, page.extract_text(), pdf_id])
        page_id = cursor.lastrowid
        if page_id is None:
            raise Exception(f"Something went wrong while inserting page {page_number} into {title}")
        cursor.execute(
                "INSERT INTO pdf_to_page (pdf_id, page_id) VALUES (?,?)", 
                [pdf_id, page_id])
    else:
        fresh_page = False
        page_id = row[0]

    extract_figures(cursor, live, page_number, title, page, page_id, args, fresh_page)

    summarize_pages(row, gists, description, args, cursor, live, page_number, title, pdf_bytes, page_id)

    insert_tables(page_number, title, args, live, rich_tables, cursor, page_id, pdf_id)

def insert_pdf(args : Namespace, the_pdf : str , live : Live, cursor : Cursor, db : Connection):

    reader = PdfReader(the_pdf)

    title = reader.metadata.title if reader.metadata and reader.metadata.title else os.path.basename(the_pdf)

    gists = [] # these are the page by page gists. We keep them around so that they can provide context for later gists

    description = generate_description(title, args, reader) if args.abstracter else None

    pdf_id = insert_pdf_by_name(title, description, cursor)

    db.commit()

    toc_and_sections = extract_toc_and_sections(reader)

    if toc_and_sections['sections']:
        insert_sections(toc_and_sections['sections'], pdf_id, cursor)

    db.commit()

    if args.embedder:
        process_pdf_for_semantic_search(
                toc_and_sections,
                cursor, pdf_id, args.embedder)

    db.commit()

    live.update(task_view(title, [f"{" " if os.getenv("NERD_FONT") else ""}Processing rich tables"]))

    rich_tables = get_rich_tables(the_pdf) if args.tables else None

    for page in reader.pages:
        insert_page(page, rich_tables, live, pdf_id, cursor, args, gists, title, description)
        db.commit()

def validate_pdf(the_pdf : str):
    with open(the_pdf, "rb") as pdf:
        header = pdf.read(4)
        if header != b'%PDF':
            sys.exit(f"Aborting. The file {the_pdf} isn't a valid PDF!")

def validate_database(the_db : str):
    with open(the_db, "rb") as database:
        #validate input
        header = database.read(6)
        if header != b'SQLite':
            sys.exit(f"Aborting. The file {the_db} isn't a valid SQLite database!")

def main():
    parser = argparse.ArgumentParser(
            prog = "pdf2sqlite",
            description = "covert pdfs into an easy-to-query sqlite DB")

    def positive_int(value):
        ival = int(value)
        if ival <= 0:
            raise argparse.ArgumentTypeError(f"lower_pixel_bound must be a positive integer, got '{value}'")
        return ival

    parser.add_argument("-p", "--pdfs",
                        help = "pdfs to add to DB", nargs="+", required= True)
    parser.add_argument("-d", "--database",
                        help = "database where PDF will be added", required= True)
    parser.add_argument("-s", "--summarizer",
                        help = "an LLM to sumarize pdf pages (litellm naming conventions)")
    parser.add_argument("-a", "--abstracter",
                        help = "an LLM to produce an abstract (litellm naming conventions)")
    parser.add_argument("-e", "--embedder",
                        help = "an embedding model to generate vector embeddings (litellm naming conventions)")
    parser.add_argument("-v", "--vision_model",
                        help = "a vision model to describe images (litellm naming conventions)")
    parser.add_argument("-t", "--tables", action = "store_true",
                        help = "use gmft to analyze tables")
    parser.add_argument("-o", "--offline", action = "store_true",
                        help = "offline mode for gmft (blocks hugging face telemetry, solves VPN issues)")
    parser.add_argument("-l", "--lower_pixel_bound", type=positive_int, default=100,
                        help = "lower bound on pixel size for images")
    args = parser.parse_args()

    if args.offline:
        os.environ['HF_HUB_OFFLINE'] = '1'

    for pdf in args.pdfs:
        validate_pdf(pdf)

    #validate database
    if os.path.exists(args.database):
        validate_database(args.database)

    with Live(fresh_view(), refresh_per_second=4) as live:
        update_db(args, live)

def update_db(args : Namespace, live : Live):

    db = sqlite3.connect(args.database)

    # check if pdf_pages table exists
    cursor = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='pdf_pages'");

    rows = cursor.fetchall()

    if len(rows) < 1:
        # if not, create it.
        live.console.print(f"[blue]{"󰪩 " if os.getenv("NERD_FONT") else ""}Initializing new database")
        init_db(cursor)

    for pdf in args.pdfs:
        insert_pdf(args, pdf, live, cursor, db)
