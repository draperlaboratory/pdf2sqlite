https://github.com/user-attachments/assets/f803902d-509e-44ca-a293-f5ff021b7e6d

# pdf2sqlite

pdf2sqlite lets you convert an arbitrarily large set of PDFs into a single
sqlite database. 

Why? Because you might want an LLM to be able to search and query within these
documents. If you have a large set of documents, you may not be able to fit
them all into the model's context window, or you may find that doing so
degrades performance.

In order to make information in the PDFs more discoverable, pdf2sqlite provides 
a variety of labeling mechanisms.

1. You can extract a short searchable "gist" of each page (using any text 
   completion model supported by [litellm](https://github.com/BerriAI/litellm)) 
   and an "abstract" for the PDF.
2. Figures and tabular data are identified within the PDF, and tabular data is 
   extracted using [gmft](https://github.com/conjuncts/gmft).
3. Figures and tables can be described by a vision model.
4. PDF Sections can be labeled with doc2vec style embedding vectors for more 
   semantic search. These are stored in the database using 
   [sqlite-vec](https://github.com/asg017/sqlite-vec).

## Usage

```
usage: pdf2sqlite [-h] -p PDFS [PDFS ...] -d DATABASE [-s SUMMARIZER] [-a 
ABSTRACTER] [-e EMBEDDER] [-v VISION_MODEL] [-t]
                  [-o] [-l LOWER_PIXEL_BOUND] [-z DECOMPRESSION_LIMIT]

convert pdfs into an easy-to-query sqlite DB

options:
  -h, --help            show this help message and exit
  -p, --pdfs PDFS [PDFS ...]
                        pdfs to add to DB
  -d, --database DATABASE
                        database where PDF will be added
  -s, --summarizer SUMMARIZER
                        an LLM to sumarize pdf pages (litellm naming conventions)
  -a, --abstracter ABSTRACTER
                        an LLM to produce an abstract (litellm naming conventions)
  -e, --embedder EMBEDDER
                        an embedding model to generate vector embeddings (litellm naming conventions)
  -v, --vision_model VISION_MODEL
                        a vision model to describe images (litellm naming conventions)
  -t, --tables          use gmft to analyze tables (will also use a vision model if available)
  -o, --offline         offline mode for gmft (blocks hugging face telemetry, solves VPN issues)
  -l, --lower_pixel_bound LOWER_PIXEL_BOUND
                        lower bound on pixel size for images
  -z, --decompression_limit DECOMPRESSION_LIMIT
                        upper bound on size for decompressed images. default 75,000,000. zero disables
```

### Invocation

You can run the latest version easily with `uvx` or `uv tool` Here's an 
example invocation (assuming you have bedrock credentials in your 
environment):

```
uvx pdf2sqlite --offline -p ../data/*.pdf -d data.db -a 
"bedrock/amazon.nova-lite-v1:0" -s "bedrock/amazon.nova-lite-v1:0" -t
```

### Integration with an LLM

Some design guidelines:

1. Pass the database schema to the LLM. The schema will contain some comments 
   that describe the different columns.

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
