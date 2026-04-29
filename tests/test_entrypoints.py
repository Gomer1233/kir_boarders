import importlib
import py_compile
from pathlib import Path


def test_main_wrapper_imports():
    importlib.import_module("main")


def test_supported_pipeline_entrypoint_imports():
    importlib.import_module("main_final_v3")


def test_supported_python_files_compile():
    for path in [Path("main.py"), Path("main_final_v3.py"), Path("scripts/merge_data.py")]:
        py_compile.compile(str(path), doraise=True)
