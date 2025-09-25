from gmft.auto import AutoTableDetector
from gmft.formatters.base import FormattedTable
from gmft.formatters.tatr import TATRFormatConfig, TATRTableFormatter
from gmft.pdf_bindings.pdfium import PyPDFium2Document

def get_rich_tables(pdf_path : str) -> list[FormattedTable]:

    detector = AutoTableDetector()
    config = TATRFormatConfig(large_table_threshold=0, no_timm=True)
    formatter = TATRTableFormatter(config=config)

    doc = PyPDFium2Document(pdf_path)

    tables = []

    for page in doc:
        tables += detector.extract(page)

    return list(map(formatter.extract, tables))
