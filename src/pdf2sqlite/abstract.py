import base64
import litellm
import sys

def abstract(title, pdf_bytes, model):

    if not litellm.utils.supports_pdf_input(model):
        sys.exit(f"Aborting. The model supplied, `{model}` doesn't support PDF input!")

    base64_string = base64.b64encode(pdf_bytes).decode("utf-8")

    response = litellm.completion(
            model = model,
            messages = [ { 
               "role" : "system",
                  "content": f"""
You are an AI document summarizer. You will be given a short PDF. This PDF contains the first few pages of a document titled {title}. Give a concise one-paragraph description of the overall topic and contents of the document.
"""
             },
            {
                "role": "user",
                "content": [                    
                    {
                        "type": "image_url",
                        "image_url":  f"data:application/pdf;base64,{base64_string}"
                    },
                    {
                        "type": "text",
                        "text" : "Please summarize this PDF."
                    },

                ],
            }])

    return response.choices[0].message.content

