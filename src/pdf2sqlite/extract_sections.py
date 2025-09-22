from pypdf import PdfReader
from pypdf.generic._data_structures import Destination
from typing import Dict

def extract_toc_and_sections(reader: PdfReader) -> Dict:
    """
    Extract table of contents and corresponding sections from a single PDF.
    If TOC is not available, fall back to heuristic section detection.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        Dictionary containing filename, TOC entries, and extracted sections
    """
    result = {
        'has_toc': False,
        'toc_entries': [],
        'sections': {}
    }

    try:
        # Extract outline/TOC if available
        outline = reader.outline
        flat_entries = []

        # Process outline entries
        if outline:
            def process_outline(entries, level=1):
                if not entries:
                    return []
                flat = []
                for entry in entries:
                    if isinstance(entry, list):
                        flat.extend(process_outline(entry, level + 1))
                    else:
                        # Include level info with the entry
                        entry.level = level
                        flat.append(entry)
                return flat

            flat_entries : list[Destination] = process_outline(outline)

            if flat_entries:
                result['has_toc'] = True
                result['toc_entries'] = flat_entries

                # Extract text from each TOC section
                for i, entry in enumerate(flat_entries):
                    if hasattr(entry, 'title') and hasattr(entry, 'page'):
                        title = entry.title or f'section {i}'
                        level = getattr(entry, 'level', 1)

                        # Get page number
                        page_number = reader.get_destination_page_number(entry)

                        if page_number is None:
                            #skip section if we can't find page numbers
                            continue

                        # Determine section end page
                        next_page = None
                        for j in range(i + 1, len(flat_entries)):
                            next_entry = flat_entries[j]
                            if getattr(next_entry, 'level', 1) <= level:
                                try:
                                    next_page = reader.get_destination_page_number(next_entry)
                                    break
                                except:
                                    pass

                        # Extract text for this section
                        section_text = ""
                        start_page = page_number
                        end_page = next_page if next_page is not None else len(reader.pages) - 1

                        for p in range(start_page, min(end_page + 1, len(reader.pages))):
                            try:
                                page_text = reader.pages[p].extract_text()
                                if page_text:
                                    section_text += page_text + "\n\n"
                            except Exception as e:
                                print(f"Error extracting text from page {p}: {e}")

                        # Store the section
                        section_id = f"{level}_{title.replace(' ', '_')[:30]}_{page_number}"
                        result['sections'][section_id] = {
                            'title': title,
                            'level': level,
                            'start_page': page_number,
                            'end_page': end_page,
                            'text': section_text
                        }

        # If no TOC was found or no valid sections were extracted, use page-based sections
        if not result['has_toc'] or not result['sections']:
            print("No TOC found or no valid sections extracted. Using page-based sections.")
            result['has_toc'] = False

            for page_num, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    section_id = f"page_{page_num + 1}"
                    result['sections'][section_id] = {
                        'title': f"Page {page_num + 1}",
                        'level': 1,
                        'start_page': page_num,
                        'end_page': page_num + 1,
                        'text': page_text
                    }

    except Exception as e:
        print(f"Error extracting TOC: {e}")

    return result
