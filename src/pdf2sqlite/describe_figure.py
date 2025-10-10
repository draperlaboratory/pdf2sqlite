import base64
import litellm
from .view import task_view
from rich.markdown import Markdown
from rich.panel import Panel

def system_prompt():
    return """
Please give a detailed description of this figure. This description will be
included in a database, and used in queries to discover the image, so you
should include as many keywords and important features of the image as you can.

Include

1. Content type (photo, chart, flowchart, blueprint, wiring diagram,  etc.)
2. Technical domain (engineering, software, medical, etc)
3. Key components, processes, or other elements shown
4. Any technical terms, labels, or specifications visible
5. Relevant technical keywords
6. Any readable text content

Be factual and specific. Do not ask follow up questions, only generate the description.

"""

def describe(image_bytes, mimetype, model, live, title, tasks):
    # previous gists could supply additional context, but let's try it
    # context-free to start

    base64_string = base64.b64encode(image_bytes).decode("utf-8")

    response = litellm.completion(
            stream = True,
            model = model,
            messages = [ { 
               "role" : "system",
                  "content": system_prompt()
             },
            {
                "role": "user",
                "content": [                    
                    {
                        "type": "image_url",
                        "image_url":  f"data:{mimetype};base64,{base64_string}"
                    },
                    {
                        "type": "text",
                        "text" : "Please describe this image."
                    },

                ],
            }])

    description = ""
    for chunk in response:
        description = description + (chunk.choices[0].delta.content or "")
        live.update(task_view(title, tasks + [Panel(Markdown(description))]))

    return description

