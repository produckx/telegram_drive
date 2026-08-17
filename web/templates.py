import os
from jinja2 import Environment, FileSystemLoader
from starlette.templating import Jinja2Templates

templates_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
jinja_env = Environment(
    loader=FileSystemLoader(templates_dir),
    auto_reload=False,
)
templates = Jinja2Templates(directory=templates_dir, env=jinja_env)