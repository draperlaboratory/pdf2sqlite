import os
import io
import base64
import sys
import sqlite3
from sqlite3 import Connection, Cursor
from PIL import Image
from pypdf import PdfReader, PdfWriter
from rich.live import Live
from rich.tree import Tree
import argparse
from argparse import Namespace
from .summarize import summarize
from .abstract import abstract
from .extract_sections import extract_toc_and_sections
from .init_db import init_db
from .pdf_to_table import get_rich_tables
from .embeddings import process_pdf_for_semantic_search
from .describe_figure import describe
from .view import set_view

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
    row : list[int] | None = cursor.fetchone()

    if row is None:
        cursor.execute("INSERT INTO pdfs (title, description) VALUES (?,?)", 
                       [title, description])
        return cursor.lastrowid
    else:
        return row[0]

def insert_sections(sections, pdf_id, cursor : Cursor):
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

def insert_page(page, rich_tables, live, pdf_id, cursor, args, gists, title):


    page_number = page.page_number + 1 #pages are zero indexed. We do this to match the probable ToC one-indexing of pages.
    live.update(set_view(page_number, title, ["extracting page"]))

    cursor.execute("SELECT id, gist FROM pdf_pages WHERE pdf_id = ? AND page_number = ?", [pdf_id, page.page_number + 1])
    row = cursor.fetchone()
    page_id = None
    new_pdf = PdfWriter(None)
    new_pdf.insert_page(page)
    pdf_bytes = io.BytesIO()
    new_pdf.write(pdf_bytes)
    pdf_bytes = pdf_bytes.getvalue()

    if row is None:
        live.update(set_view(page_number, title, ["extracting page", "extracting text"]))
        cursor.execute(
                "INSERT INTO pdf_pages (page_number, data, text, pdf_id) VALUES (?,?,?,?)",
                [page_number, pdf_bytes, page.extract_text(), pdf_id])
        page_id = cursor.lastrowid
        cursor.execute(
                "INSERT INTO pdf_to_page (pdf_id, page_id) VALUES (?,?)", 
                [pdf_id, page_id])

        live.update(set_view(page_number, title, ["extracting page", "extracting figures"]))
        total = len(page.images)
        for index, fig in enumerate(page.images):
            live.update(set_view(page_number, title, 
                ["extracting page", "extracting figures", f"extracting figure {index+1}/{total}"]))
            mime_type = Image.MIME.get(fig.image.format.upper())
            description = None
            cursor.execute("INSERT INTO pdf_figures (data, description, mime_type) VALUES (?,?,?)", 
                           [fig.data, description, mime_type])
            figure_id = cursor.lastrowid
            cursor.execute("INSERT INTO page_to_figure (page_id, figure_id) VALUES (?,?)",
                           [page_id, figure_id])
    else:
        page_id = row[0]

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
            tasks = ["extracting page", "describing figures", f"describing figure {index+1}/{total}"]
            if fig[0] is None:
                description = describe(fig[2], fig[3], args.vision_model, live, page_number, title, tasks)
                cursor.execute("UPDATE pdf_figures SET description = ? WHERE id = ?",
                               [description, fig[1]])

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
        live.update(set_view(page_number, title, 
             ["extracting page", "adding page summaries", f"inserting gist: {gist}"]))

    if args.tables:
        live.update(set_view(page_number, title, 
             ["extracting page", "inserting tables"]))
        total = len(rich_tables)
        for index, table in enumerate(rich_tables):
            if table.page.page_number + 1 == page_number:
                buffered = io.BytesIO()
                table.image().save(buffered, format="JPEG")
                image_b64 = base64.b64encode(buffered.getvalue())
                try:
                    live.update(set_view(page_number, title, 
                         ["extracting page", "inserting tables", f"inserting table: {index+1}/{total}"]))
                    text = table.df().to_markdown()
                    cursor.execute(
                            "INSERT INTO pdf_tables (text, image, caption_above, caption_below, pdf_id, page_number, xmin, ymin) VALUES (?,?,?,?,?,?,?,?)",
                            [text, image_b64, table.captions()[0], table.captions()[1], pdf_id, page_number, table.bbox[0], table.bbox[1]])
                    table_id = cursor.lastrowid
                    cursor.execute(
                            "INSERT INTO page_to_table (page_id, table_id) VALUES (?,?)",
                            [page_id, table_id])
                except:
                        live.console.print(f"[red]extract table on p{page_number} failed")
                        text = None

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

    rich_tables = get_rich_tables(the_pdf) if args.tables else None

    for index, page in enumerate(reader.pages):
        insert_page(page, rich_tables, live, pdf_id, cursor, args, gists, title)
        db.commit()

def validate_pdf(the_pdf):
    with open(the_pdf, "rb") as pdf:
        header = pdf.read(4)
        if header != b'%PDF':
            sys.exit("Aborting. The input file isn't a valid PDF!")

def main():
    parser = argparse.ArgumentParser(
            prog = "pdf2sqlite",
            description = "covert pdfs into an easy-to-query sqlite DB")

    parser.add_argument("-p", "--pdfs", help = "pdfs to add to DB", nargs="+", required= True)
    parser.add_argument("-d", "--database", help = "database where PDF will be added", required= True)
    parser.add_argument("-s", "--summarizer", help = "an LLM to sumarize pdf pages (litellm naming conventions)")
    parser.add_argument("-a", "--abstracter", help = "an LLM to produce an abstract (litellm naming conventions)")
    parser.add_argument("-e", "--embedder", help = "an embedding model to generate vector embeddings (litellm naming conventions)")
    parser.add_argument("-v", "--vision_model", help = "a vision model to describe images (litellm naming conventions)")
    parser.add_argument("-t", "--tables", action = "store_true", help = "use gmft to analyze tables")
    parser.add_argument("-o", "--offline", action = "store_true", help = "offline mode for gmft (blocks hugging face telemetry, solves VPN issues)")

    args = parser.parse_args()

    if args.offline:
        os.environ['HF_HUB_OFFLINE'] = '1'

    for pdf in args.pdfs:
        validate_pdf(pdf)

    #validate database
    if os.path.exists(args.database):
        with open(args.database, "rb") as database:
            #validate input
            header = database.read(6)
            if header != b'SQLite':
                sys.exit("Aborting. The input file isn't a valid SQLite database!")

    view = Tree("")

    with Live(view, refresh_per_second=4) as live:
        update_db(args, live)

def update_db(args : Namespace, live : Live):

    db = sqlite3.connect(args.database)

    # check if pdf_pages table exists
    cursor = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='pdf_pages'");

    rows = cursor.fetchall()

    if len(rows) < 1:
        # if not, create it.
        live.console.print("[blue]Initializing new database")
        init_db(cursor)

    for pdf in args.pdfs:
        insert_pdf(args, pdf, live, cursor, db)
