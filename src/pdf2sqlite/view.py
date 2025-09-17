from rich.markdown import Markdown
from rich.tree import Tree

def set_view(page_nu, title, tasks = []):
    tree = Tree(Markdown(f"**processing page {page_nu} of {title}**"))
    for task in tasks:
        tree.add(task)
    return tree
