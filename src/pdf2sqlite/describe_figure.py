import base64
import litellm
import sys

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

def describe(image_bytes, mimetype, model):
    # previous gists could supply additional context, but let's try it
    # context-free to start

    if not litellm.supports_vision(model):
        sys.exit(f"Aborting. The model supplied, `{model}` doesn't support image inputs!")

    base64_string = base64.b64encode(image_bytes).decode("utf-8")

    response = litellm.completion(
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

    return response.choices[0].message.content

