from __future__ import annotations

# Smoke manual contra la API real de Scanéame. NO es un test: se renombró
# desde scripts/test_scaneame.py (colisionaba con tests/test_scaneame.py y
# el nombre tentaba a lanzarlo bajo pytest gastando cuota de la API real).
# Nunca envía nada sin el flag --live.

import argparse
import asyncio
import json
import mimetypes
import sys
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.services.scaneame import ScaneameError, extract_ticket


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Envía un documento al endpoint tickets de Scanéame (API real)."
    )
    parser.add_argument(
        "document",
        nargs="?",
        type=Path,
        default=ROOT / "data" / "sample.jpg",
        help="Documento que se procesará (por defecto: data/sample.jpg).",
    )
    parser.add_argument(
        "--content-type",
        help="MIME type opcional; por defecto se deduce de la extensión.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Obligatorio para enviar la petición real; sin él no se llama a la API.",
    )
    return parser.parse_args()


async def _run(document: Path, content_type: str) -> None:
    result = await extract_ticket(document.read_bytes(), content_type)
    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))


def main() -> int:
    args = _arguments()
    if not args.live:
        print(
            "Este smoke llama a la API real de Scanéame y gasta cuota. "
            "Repassa que SCANEAME_API_KEY es la correcta y re-ejecuta con --live.",
            file=sys.stderr,
        )
        return 2

    document = args.document.expanduser().resolve()
    if not document.is_file():
        print(f"ERROR: no existe el documento: {document}", file=sys.stderr)
        return 2

    content_type = args.content_type or mimetypes.guess_type(document.name)[0]
    if not content_type:
        print(
            "ERROR: no se pudo deducir el Content-Type; usa --content-type.",
            file=sys.stderr,
        )
        return 2

    print(
        f"Procesando {document.name} ({content_type}, {document.stat().st_size} bytes)...",
        file=sys.stderr,
    )
    try:
        asyncio.run(_run(document, content_type))
    except (ScaneameError, httpx.HTTPError) as exc:
        print(f"ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
