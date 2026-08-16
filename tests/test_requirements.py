"""Guards dependencies that only fail somewhere other than a developer machine.

`python-multipart` was missing from requirements.txt for the whole life of the
upload endpoint. Locally it was installed as a transitive dependency of
something else, so every test passed; CI installs only what is declared, and
every API test failed at *collection* — FastAPI raises when it builds a route
declaring `UploadFile`, not when that route is called, so one missing package
took the entire app down rather than one endpoint.

Nothing in the toolchain notices a package that is installed but undeclared,
which is exactly the shape of bug worth a test.
"""

import re
from importlib import import_module
from importlib.util import find_spec

import pytest

from config.settings import BASE_DIR

REQUIREMENTS = BASE_DIR / "requirements.txt"

#: Distribution name in requirements.txt → module it provides. Only packages
#: that must be importable for `api.app` to import at all belong here.
IMPORT_TIME_DEPENDENCIES = {
    "python-multipart": "multipart",
    "fastapi": "fastapi",
    "pydantic": "pydantic",
}


def _declared() -> set[str]:
    """Distribution names in requirements.txt, without version specifiers."""
    names = set()
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        # "uvicorn[standard]>=0.30.0" -> "uvicorn"
        names.add(re.split(r"[\[<>=!;]", line)[0].strip().lower())
    return names


@pytest.mark.parametrize("distribution", sorted(IMPORT_TIME_DEPENDENCIES))
def test_import_time_dependency_is_declared(distribution: str) -> None:
    assert distribution in _declared(), (
        f"{distribution} is needed to import api.app but is not in "
        f"requirements.txt — CI installs only what is declared."
    )


@pytest.mark.parametrize(
    "distribution, module", sorted(IMPORT_TIME_DEPENDENCIES.items())
)
def test_declared_dependency_is_actually_importable(
    distribution: str, module: str
) -> None:
    """The mapping above is only useful while it names real modules."""
    assert find_spec(module) is not None, f"{distribution} provides no {module}"


def test_the_app_imports_with_its_upload_route() -> None:
    """The failure this file exists for: a route FastAPI cannot build."""
    app = import_module("api.app").create_app()
    # Read it off the schema rather than app.routes: building the schema is
    # what forces FastAPI to resolve the UploadFile parameter.
    assert "post" in app.openapi()["paths"]["/documents"]
