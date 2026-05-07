from __future__ import annotations

from importlib.resources import as_file, files
from pathlib import Path
from typing import Iterator
from contextlib import contextmanager


@contextmanager
def resource_path(name: str) -> Iterator[Path]:
    resource = files("voice_input.resources").joinpath(name)
    with as_file(resource) as path:
        yield path
