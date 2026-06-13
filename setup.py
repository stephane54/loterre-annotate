import os
from setuptools import setup

_here = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(_here, "VERSION")) as f:
    VERSION = f.read().strip()

with open(os.path.join(_here, "requirements.txt")) as f:
    install_requires = [
        line.strip() for line in f
        if line.strip() and not line.startswith("#")
    ]

setup(
    name="loterre-annotate",
    version=VERSION,
    zip_safe=False,
    author="Stephane Schneider",
    author_email="stephane.schneider@inist.fr",
    description="Moteur d'annotation terminologique sur les vocabulaires Loterre (v9)",
    url="https://github.com/stephane54/loterre-annotate.git",
    python_requires=">=3.9",
    license="GPL v3",
    package_dir={"": "src"},
    py_modules=[
        "loterre_cli",
        "loterre_engine_v9_cli",
        "loterre_fast_path",
        "loterre_html_renderer",
        "loterre_api_eval",
        "loterre_benchmark",
    ],
    install_requires=install_requires,
    entry_points={
        "console_scripts": [
            "loterre-annotate  = loterre_cli:main",
            "loterre-engine    = loterre_engine_v9_cli:main",
            "loterre-benchmark = loterre_benchmark:main",
            "loterre-render    = loterre_html_renderer:main",
        ]
    },
)
