CREATE TABLE pdfs(
    id INTEGER PRIMARY KEY,
    description STRING,
    title STRING NOT NULL UNIQUE
);

CREATE TABLE pdf_to_page(
    pdf_id INTEGER NOT NULL,
    page_id INTEGER NOT NULL,
    FOREIGN KEY (pdf_id) REFERENCES pdfs(id) ON DELETE CASCADE,
    FOREIGN KEY (page_id) REFERENCES pdf_pages(id) ON DELETE CASCADE,
    PRIMARY KEY (pdf_id, page_id)
);

CREATE TABLE pdf_pages(
    id INTEGER PRIMARY KEY,
    page_number INT,
    gist STRING,
    text STRING,
    data BLOB, --This is binary data for this page as a standalone PDF
    pdf_id INTEGER NOT NULL,
    FOREIGN KEY (pdf_id) REFERENCES pdfs(id) ON DELETE CASCADE,
    UNIQUE (pdf_id, page_number)
);

CREATE TABLE pdf_to_section(
    pdf_id INTEGER NOT NULL,
    section_id INTEGER NOT NULL,
    FOREIGN KEY (pdf_id) REFERENCES pdfs(id) ON DELETE CASCADE,
    FOREIGN KEY (section_id) REFERENCES pdf_sections(id) ON DELETE CASCADE,
    PRIMARY KEY (pdf_id, section_id)
);

CREATE TABLE pdf_sections(
    id INTEGER PRIMARY KEY,
    start_page INT,
    title STRING,
    gist STRING,
    pdf_id INTEGER NOT NULL,
    FOREIGN KEY (pdf_id) REFERENCES pdfs(id) ON DELETE CASCADE,
    UNIQUE (title, pdf_id)
);

CREATE TABLE pdf_tables(
    id INTEGER PRIMARY KEY,
    text STRING, --extracted markdown text
    image BLOB, --This is binary data for an image of the table
    description STRING, --a description of the table contents
    caption_above STRING,
    caption_below STRING,
    pdf_id INTEGER NOT NULL,
    page_number INTEGER NOT NULL,
    ymin INTEGER NOT NULL,
    xmin INTEGER NOT NULL,
    UNIQUE (pdf_id, page_number, ymin, xmin)
);

CREATE TABLE pdf_figures(
    id INTEGER PRIMARY KEY,
    mime_type STRING NOT NULL, --the mime type of the image
    description STRING, --a description of the image contents
    data BLOB --this is binary data for an image of the figure
);

CREATE TABLE page_to_table(
    -- This table holds the relation between pages and tables, and can be used to look up the tables on a given page using a JOIN
    page_id INTEGER NOT NULL,
    table_id INTEGER NOT NULL,
    FOREIGN KEY (page_id) REFERENCES pdf_pages(id) ON DELETE CASCADE,
    FOREIGN KEY (table_id) REFERENCES pdf_tables(id) ON DELETE CASCADE,
    PRIMARY KEY (page_id, table_id)
);

CREATE TABLE page_to_figure(
    -- This table holds the relation between pages and figures, and can be used to look up the figures on a given page using a JOIN
    page_id INTEGER NOT NULL,
    figure_id INTEGER NOT NULL,
    FOREIGN KEY (page_id) REFERENCES pdf_pages(id) ON DELETE CASCADE,
    FOREIGN KEY (figure_id) REFERENCES pdf_figures(id) ON DELETE CASCADE,
    PRIMARY KEY (page_id, figure_id)
);

-- Create vec0 virtual table for efficient vector storage
-- Adjust dimension based on the embedding model being used (default to 1024 for Mistral)
CREATE VIRTUAL TABLE IF NOT EXISTS section_embeddings_vec USING vec0(
    embedding float[1024]
);

CREATE TABLE IF NOT EXISTS section_vec_mapping(
    section_id INTEGER PRIMARY KEY,
    vec_rowid INTEGER NOT NULL,
    FOREIGN KEY (section_id) REFERENCES pdf_sections(id) ON DELETE CASCADE
);

-- Table for section topics/clusters
CREATE TABLE IF NOT EXISTS section_topics(
    id INTEGER PRIMARY KEY,
    section_id INTEGER NOT NULL,
    topic_id INTEGER NOT NULL,
    confidence REAL,
    FOREIGN KEY (section_id) REFERENCES pdf_sections(id) ON DELETE CASCADE
    FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE
);

-- Table for topics/clusters
CREATE TABLE IF NOT EXISTS topics(
    id INTEGER PRIMARY KEY,
    name TEXT,
    description TEXT
);

-- Table for section keywords
CREATE TABLE IF NOT EXISTS section_keywords(
    id INTEGER PRIMARY KEY,
    section_id INTEGER NOT NULL,
    keywords TEXT NOT NULL,
    FOREIGN KEY (section_id) REFERENCES pdf_sections(id) ON DELETE CASCADE
    );
