from __future__ import annotations

import argparse
import importlib.util
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ConversionContext:
    input_path: Path
    output_path: Path
    work_dir: Path


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a user-authored Python PDF conversion script.",
    )
    parser.add_argument("--script", required=True, help="Path to a Python script that defines convert(context).")
    parser.add_argument("--input", required=True, help="Input PDF path.")
    parser.add_argument("--output", required=True, help="Output PDF path.")
    parser.add_argument(
        "--work-dir",
        default="data/work",
        help="Scratch directory for intermediate files created by the script.",
    )
    return parser.parse_args(argv)


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("pdf_linker_user_converter", script_path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Unable to load converter script: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_converter_script(script_path: Path, input_path: Path, output_path: Path, work_dir: Path) -> Path:
    script_path = script_path.expanduser().resolve()
    input_path = input_path.expanduser().resolve()
    output_path = output_path.expanduser().resolve()
    work_dir = work_dir.expanduser().resolve()

    if not script_path.exists():
        raise SystemExit(f"Converter script does not exist: {script_path}")
    if not input_path.exists():
        raise SystemExit(f"Input PDF does not exist: {input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    module = _load_module(script_path)
    convert = getattr(module, "convert", None)
    if not callable(convert):
        raise SystemExit(f"Converter script must define a callable convert(context): {script_path}")

    context = ConversionContext(
        input_path=input_path,
        output_path=output_path,
        work_dir=work_dir,
    )
    convert(context)
    if not output_path.exists():
        raise SystemExit(f"Converter script finished without creating output: {output_path}")
    return output_path


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    run_converter_script(
        script_path=Path(args.script),
        input_path=Path(args.input),
        output_path=Path(args.output),
        work_dir=Path(args.work_dir),
    )
    return 0
