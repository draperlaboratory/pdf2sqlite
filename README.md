# pdf2sqlite

pdf2sqlite lets you convert an arbitrarily large set of PDFs into a single
sqlite database. 

Why? Because you might want an LLM to be able to search and query within these
documents. If you have a large set of documents, you may not be able to fit
them all into the model's context window, or you may find that doing so
degrades performance.

In order to make information in the PDFs more discoverable, pdf2sqlite lets you
extract a "gist" of each page (using any model supported by litellm) and an
"abstract" for the PDF. Figures and tabular data are identified within the PDF,
and tabular data extracted using [gmft](https://github.com/conjuncts/gmft).

```
usage: pdf2sqlite [-h] -p PDFS [PDFS ...] -d DATABASE [-s SUMMARIZER] [-a 
ABSTRACTER] [-e EMBEDDER] [-v VISION_MODEL] [-t] [-o]

covert pdfs into an easy-to-query sqlite DB

options:
  -h, --help            show this help message and exit
  -p PDFS [PDFS ...], --pdfs PDFS [PDFS ...]
                        pdfs to add to DB
  -d DATABASE, --database DATABASE
                        database where PDF will be added
  -s SUMMARIZER, --summarizer SUMMARIZER
                        an LLM to sumarize pdf pages (litellm naming conventions)
  -a ABSTRACTER, --abstracter ABSTRACTER
                        an LLM to produce an abstract (litellm naming conventions)
  -e EMBEDDER, --embedder EMBEDDER
                        an embedding model to generate vector embeddings (litellm naming conventions)
  -v VISION_MODEL, --vision_model VISION_MODEL
                        a vision model to describe images (litellm naming conventions)
  -t, --tables          use gmft to analyze tables
  -o, --offline         offline mode for gmft (blocks hugging face telemetry, solves VPN issues)
```

## Usage

### Invocation

Here's an example invocation:

```
uv run uv run pdf2sqlite --offline -p ../data/*.pdf -d data.db -a "bedrock/amazon.nova-lite-v1:0" -s "bedrock/amazon.nova-lite-v1:0" -t
```

### Integration with an LLM

Some design guidelines:

1. Pass the database schema to the LLM. It will contain some comments that
   describe the different columns.

2. To get the most of the database, you will probably want to write a tool that
   your LLM can call to convert binary pdf and image data stored in the
   database into images and PDF pages. A good design is to allow the LLM to
   pass in a table name, row id and column name, and receive the relevant
   content as a response. The LLM will generally be able to discern the
   necessary inputs from the schema, so the tool will be robust against future
   schema changes.

3. A backend (like, e.g. Amazon Bedrock) that supports returning PDFs as the
   result of a tool call may be helpful, although it will probably work to
   return the PDF as a separate content block alongside a tool call result that
   just says "success, PDF will be delivered" or something similar.
