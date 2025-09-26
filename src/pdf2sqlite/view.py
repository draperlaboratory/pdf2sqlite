import os
from rich.markdown import Markdown
from rich.tree import Tree

def task_view(title, tasks = []):
    tree = Tree(Markdown(f"{"󰗚" if os.environ["NERD_FONT"] else ""} **Processing {title}**"))
    for task in tasks:
        tree.add(task)
    return tree

def fresh_view():
    return Tree("")
