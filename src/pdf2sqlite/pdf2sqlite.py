import os
import io
import base64
import sys
import sqlite3
from pypdf import PdfReader, PdfWriter
import argparse
from .summarize import summarize
from .abstract import abstract
from .extract_sections import extract_toc_and_sections
from .init_db import init_db
from .pdf_to_table import get_rich_tables
from .embeddings import process_pdf_for_semantic_search

def generate_description(title, args, reader):
    if args.abstracter:
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
    else:
        return None

def insert_pdf_by_name(title, description, cursor):
    cursor.execute("SELECT id FROM pdfs WHERE title = ?", [title])
    row = cursor.fetchone()

    if row is None:
        cursor.execute("INSERT INTO pdfs (title, description) VALUES (?,?)", 
                       [title, description])
        return cursor.lastrowid
    else:
        return row[0]

def insert_pdf(args, the_pdf, cursor, db):

    reader = PdfReader(the_pdf)

    title = reader.metadata.title or os.path.basename(the_pdf)

    description = generate_description(title, args, reader)

    pdf_id = insert_pdf_by_name(title, description, cursor)

    db.commit()

    toc_and_sections = extract_toc_and_sections(reader)

    if toc_and_sections['sections']:
        for section_key, section in toc_and_sections['sections'].items():
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
                    db.commit()

    if args.embedder:
        process_pdf_for_semantic_search(
                toc_and_sections,
                cursor,
                pdf_id,
                args.embedder)

    db.commit()

    gists = [] # these are the page by page gists. We keep them around so that they can provide context for later gists

    if args.tables:
        rich_tables = get_rich_tables(the_pdf)

    for index, page in enumerate(reader.pages):
        page_number = page.page_number + 1 #pages are zero indexed, we do this to match the probable ToC one-indexing of pages
        cursor.execute("SELECT id, gist FROM pdf_pages WHERE pdf_id = ? AND page_number = ?", [pdf_id, page.page_number + 1])
        row = cursor.fetchone()
        page_id = None
        new_pdf = PdfWriter(None)
        new_pdf.insert_page(page)
        pdf_bytes = io.BytesIO()
        new_pdf.write(pdf_bytes)
        pdf_bytes = pdf_bytes.getvalue()
        if row is None:
            print(f"creating page {index}")
            cursor.execute(
                    "INSERT INTO pdf_pages (page_number, data, text, pdf_id) VALUES (?,?,?,?)",
                    [page_number, pdf_bytes, page.extract_text(), pdf_id])
            page_id = cursor.lastrowid
            cursor.execute(
                    "INSERT INTO pdf_to_page (pdf_id, page_id) VALUES (?,?)", 
                    [pdf_id, page_id])

            for count, fig in enumerate(page.images):
                cursor.execute("INSERT INTO pdf_figures (data, mime_type) VALUES (?,?)", [fig.data, fig.image.format])
                figure_id = cursor.lastrowid
                cursor.execute("INSERT INTO page_to_figure (page_id, figure_id) VALUES (?,?)",
                               [page_id, figure_id])
        else:
            page_id = row[0]

        if (row is None or row[1] is None) and args.summarizer:
            gist = summarize(gists,
                             description,
                             page_number,
                             the_pdf,
                             pdf_bytes, 
                             args.summarizer)
            gists.append(gist)
            if (len(gists) > 5):
                gists.pop(0)
            cursor.execute("UPDATE pdf_pages SET gist = ? WHERE id = ?", [gist, page_id])
            print(f"adding gist of page {page_number}: {gist}")

        if args.tables:
            for table in rich_tables:
                if table.page.page_number + 1 == page_number:
                    print(f"inserting tables from page {page_number}")
                    buffered = io.BytesIO()
                    table.image().save(buffered, format="JPEG")
                    image_b64 = base64.b64encode(buffered.getvalue())
                    try:
                        print("inserted")
                        text = table.df().to_markdown()
                        cursor.execute(
                                "INSERT INTO pdf_tables (text, image, caption_above, caption_below, pdf_id, page_number, xmin, ymin) VALUES (?,?,?,?,?,?,?,?)",
                                [text, image_b64, table.captions()[0], table.captions()[1], pdf_id, page_number, table.bbox[0], table.bbox[1]])
                        table_id = cursor.lastrowid
                        cursor.execute(
                                "INSERT INTO page_to_table (page_id, table_id) VALUES (?,?)",
                                [page_id, table_id])
                    except:
                        print("extract failed")
                        text = None
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

    update_db(args)

def update_db(args):

    db = sqlite3.connect(args.database)

    # check if pdf_pages table exists
    cursor = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='pdf_pages'");
    rows = cursor.fetchall()
    if len(rows) < 1:
        # if not, create it.
        print("initializing new database")
        init_db(cursor)

    for pdf in args.pdfs:
        insert_pdf(args, pdf, cursor, db)
