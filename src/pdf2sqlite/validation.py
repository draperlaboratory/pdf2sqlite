import sys
import os
from argparse import Namespace
import litellm

def validate_args(args: Namespace):
    for pdf in args.pdfs:
        validate_pdf(pdf)

    if os.path.exists(args.database):
        validate_database(args.database)

    validate_llms(args)

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

def validate_llms(args : Namespace):

    if (args.vision_model):
        if not litellm.utils.supports_vision(args.vision_model):
            sys.exit(f"Aborting. The vision model supplied, `{args.vision_model}` doesn't support image inputs!")

    if (args.summarizer):
        if not litellm.utils.supports_pdf_input(args.summarizer):
            sys.exit(f"Aborting. The summarization model supplied, `{args.summarizer}` doesn't support PDF input!")

    if (args.abstracter):
        if not litellm.utils.supports_pdf_input(args.abstracter):
            sys.exit(f"Aborting. The abstracter model supplied, `{args.abstracter}` doesn't support PDF input!")
