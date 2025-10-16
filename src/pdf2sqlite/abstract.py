import base64
import litellm
from rich.markdown import Markdown
from rich.panel import Panel

from .task_stack import TaskStack

def systemPrompt(title):
    return (
            " You are an AI document summarizer. "
            "You will be given a short PDF. "
            f"This PDF contains the first few pages of a document titled {title}. "
            "Give a concise one-paragraph description of the overall topic and contents of the document."
            )

def abstract(title, pdf_bytes, model, tasks: TaskStack):

    base64_string = base64.b64encode(pdf_bytes).decode("utf-8")

    response = litellm.completion(
            stream = True,
            model = model,
            messages = [ { 
               "role" : "system",
                  "content": systemPrompt(title)
             },
            {
                "role": "user",
                "content": [                    
                    {
                        "type": "text",
                        "text" : "Please summarize this page."
                    },
                    {
                        "type": "file",
                        "file":  {
                            "file_data": f"data:application/pdf;base64,{base64_string}"
                        },
                    },
                ],
            }])

    description = ""
    for chunk in response:
        description = description + (chunk.choices[0].delta.content or "")
        tasks.render([Panel(Markdown(description))])

    return description

