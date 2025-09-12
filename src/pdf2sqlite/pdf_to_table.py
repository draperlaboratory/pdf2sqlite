from gmft.auto import CroppedTable, TableDetector, AutoTableDetector
from gmft.formatters.tatr import TATRFormatConfig, TATRTableFormatter
from gmft.pdf_bindings import PyPDFium2Document
from gmft._rich_text.rich_page import embed_tables

def get_rich_tables(pdf_path):

    detector = AutoTableDetector()
    config = TATRFormatConfig(large_table_threshold=0, no_timm=True)
    formatter = TATRTableFormatter(config=config)

    doc = PyPDFium2Document(pdf_path)

    tables = []

    for page in doc:
        tables += detector.extract(page)

    return list(map(formatter.extract, tables))
