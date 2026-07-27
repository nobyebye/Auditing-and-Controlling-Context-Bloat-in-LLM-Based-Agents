"""Create a DOCX working copy from a DOTX template without rewriting its parts."""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


TEMPLATE_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "wordprocessingml.template.main+xml"
)
DOCUMENT_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "wordprocessingml.document.main+xml"
)
LEGACY_CORE_RELATIONSHIP = (
    "http://schemas.openxmlformats.org/officedocument/"
    "2006/relationships/metadata/core-properties"
)
STANDARD_CORE_RELATIONSHIP = (
    "http://schemas.openxmlformats.org/package/"
    "2006/relationships/metadata/core-properties"
)


def instantiate(template: Path, output: Path) -> None:
    if template.resolve() == output.resolve():
        raise ValueError("Output must not overwrite the retained template.")
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")

    output.parent.mkdir(parents=True, exist_ok=True)
    content_types_seen = False

    with zipfile.ZipFile(template, "r") as source:
        with zipfile.ZipFile(output, "x") as target:
            for info in source.infolist():
                data = source.read(info.filename)
                if info.filename == "[Content_Types].xml":
                    content_types_seen = True
                    text = data.decode("utf-8")
                    if TEMPLATE_CONTENT_TYPE not in text:
                        raise ValueError(
                            "The package does not declare a Word template main part."
                        )
                    data = text.replace(
                        TEMPLATE_CONTENT_TYPE, DOCUMENT_CONTENT_TYPE, 1
                    ).encode("utf-8")
                elif info.filename == "_rels/.rels":
                    data = data.decode("utf-8").replace(
                        LEGACY_CORE_RELATIONSHIP, STANDARD_CORE_RELATIONSHIP
                    ).encode("utf-8")
                target.writestr(info, data)

    if not content_types_seen:
        output.unlink(missing_ok=True)
        raise ValueError("The template package has no [Content_Types].xml part.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("template", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    instantiate(args.template, args.output)
    print(f"Instantiated DOCX: {args.output}")


if __name__ == "__main__":
    main()
