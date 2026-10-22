"""Limpa arquivos dispensaveis do bundle onedir do CVJTICKET.

Por padrao apenas simula. Use --apply para remover os arquivos encontrados.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


APP_NAME = "CVJTICKET"
PROJECT_DIR = Path(__file__).resolve().parent

TZDATA_KEEP = {
    "zones",
    "zoneinfo/UTC",
    "zoneinfo/UCT",
    "zoneinfo/Universal",
    "zoneinfo/Zulu",
    "zoneinfo/Etc/UTC",
    "zoneinfo/Etc/GMT",
    "zoneinfo/America/Sao_Paulo",
    "zoneinfo/Brazil/East",
    "zoneinfo/iso3166.tab",
    "zoneinfo/zone.tab",
    "zoneinfo/zone1970.tab",
    "zoneinfo/zonenow.tab",
    "zoneinfo/tzdata.zi",
    "zoneinfo/leapseconds",
}

PROTECTED_DESKTOP_DUPLICATES = (
    "vcruntime",
    "msvcp",
)


@dataclass(frozen=True)
class Removal:
    path: str
    size: int
    reason: str


def relative_posix(path: Path, base: Path) -> str:
    return path.relative_to(base).as_posix()


def validate_internal_dir(internal: Path) -> Path:
    internal = internal.resolve()
    if internal.name.lower() != "_internal":
        raise ValueError(f'O diretorio deve terminar em "_internal": {internal}')
    if not internal.is_dir():
        raise FileNotFoundError(f"Diretorio nao encontrado: {internal}")

    app_dir = internal.parent
    executable = app_dir / f"{APP_NAME}.exe"
    if app_dir.name.upper() != APP_NAME or not executable.is_file():
        raise ValueError(
            "Protecao acionada: a pasta nao parece ser uma distribuicao "
            f"{APP_NAME} valida ({executable} nao encontrado)."
        )
    return internal


def find_removals(internal: Path, aggressive: bool) -> list[Removal]:
    removals: dict[Path, Removal] = {}

    def add(path: Path, reason: str) -> None:
        if path.is_file() and path not in removals:
            removals[path] = Removal(
                path=relative_posix(path, internal),
                size=path.stat().st_size,
                reason=reason,
            )

    # O app usa AppView.WEB_BROWSER e nao inicia o cliente Flutter desktop.
    # O hook do Flet duplica parte dessas DLLs tanto nesta pasta quanto na raiz.
    desktop_dir = internal / "flet_desktop"
    desktop_runtime = desktop_dir / "app" / "flet"
    if desktop_runtime.is_dir():
        for root_file in internal.iterdir():
            if not root_file.is_file():
                continue
            if root_file.name.lower().startswith(PROTECTED_DESKTOP_DUPLICATES):
                continue
            desktop_copy = desktop_runtime / root_file.name
            if desktop_copy.is_file() and desktop_copy.stat().st_size == root_file.stat().st_size:
                add(root_file, "DLL duplicada do runtime Flet desktop")

    if desktop_dir.is_dir():
        for path in desktop_dir.rglob("*"):
            add(path, "runtime Flet desktop nao utilizado")

    web_dir = internal / "flet_web" / "web"
    if web_dir.is_dir():
        for path in web_dir.rglob("*.symbols"):
            add(path, "simbolos de depuracao WebAssembly")

    tzdata_dir = internal / "tzdata"
    if tzdata_dir.is_dir():
        for path in tzdata_dir.rglob("*"):
            if not path.is_file():
                continue
            if relative_posix(path, tzdata_dir) not in TZDATA_KEEP:
                add(path, "fuso horario nao utilizado pelo servidor")

    # Nao ha import de tkinter no CVJTICKET; este binding opcional do Pillow
    # nao participa da geracao dos PDFs nem dos QR Codes.
    pil_dir = internal / "PIL"
    if pil_dir.is_dir():
        for path in pil_dir.glob("_imagingtk*.pyd"):
            add(path, "binding Pillow/Tk nao utilizado")

    for directory_name in ("_tcl_data", "_tk_data", "tcl8"):
        directory = internal / directory_name
        if directory.is_dir():
            for path in directory.rglob("*"):
                add(path, "runtime Tcl/Tk nao utilizado")
    for file_name in ("_tkinter.pyd", "tcl86t.dll", "tk86t.dll"):
        add(internal / file_name, "runtime Tcl/Tk nao utilizado")

    if aggressive:
        pyodide_dir = web_dir / "pyodide"
        if pyodide_dir.is_dir():
            for path in pyodide_dir.rglob("*"):
                add(path, "runtime Pyodide nao usado (modo agressivo)")

    return sorted(removals.values(), key=lambda item: item.path.lower())


def remove_files(internal: Path, removals: list[Removal]) -> None:
    for item in removals:
        target = (internal / Path(item.path)).resolve()
        if os.path.commonpath((str(internal), str(target))) != str(internal):
            raise ValueError(f"Caminho inseguro recusado: {target}")
        target.unlink(missing_ok=True)

    directories = sorted(
        (path for path in internal.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for directory in directories:
        try:
            directory.rmdir()
        except OSError:
            pass


def format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.2f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def write_manifest(
    internal: Path, removals: list[Removal], *, applied: bool, aggressive: bool
) -> Path:
    name = "limpeza_manifest.json" if applied else "limpeza_simulacao.json"
    manifest = internal.parent / name
    payload = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "internal_dir": str(internal),
        "applied": applied,
        "aggressive": aggressive,
        "removed_file_count": len(removals) if applied else 0,
        "candidate_file_count": len(removals),
        "candidate_bytes": sum(item.size for item in removals),
        "files": [asdict(item) for item in removals],
    }
    manifest.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Limpa com seguranca o _internal do CVJTICKET."
    )
    parser.add_argument(
        "internal",
        nargs="?",
        type=Path,
        default=PROJECT_DIR / "dist" / APP_NAME / "_internal",
        help="pasta _internal (padrao: dist/CVJTICKET/_internal)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="executa a remocao; sem esta opcao faz apenas uma simulacao",
    )
    parser.add_argument(
        "--aggressive",
        action="store_true",
        help="remove tambem o runtime Pyodide; exige teste completo da interface",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        internal = validate_internal_dir(args.internal)
        removals = find_removals(internal, args.aggressive)
        total_size = sum(item.size for item in removals)
        mode = "APLICACAO" if args.apply else "SIMULACAO"

        print(f"[{mode}] {internal}")
        print(f"Arquivos candidatos: {len(removals)}")
        print(f"Espaco recuperavel: {format_size(total_size)}")

        by_reason: dict[str, list[Removal]] = {}
        for item in removals:
            by_reason.setdefault(item.reason, []).append(item)
        for reason, items in sorted(by_reason.items()):
            size = sum(item.size for item in items)
            print(f"  - {reason}: {len(items)} arquivo(s), {format_size(size)}")

        if args.apply:
            remove_files(internal, removals)
            print("Limpeza concluida.")
        else:
            print("Nada foi removido. Use --apply para confirmar a limpeza.")

        manifest = write_manifest(
            internal, removals, applied=args.apply, aggressive=args.aggressive
        )
        print(f"Manifesto: {manifest}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"ERRO: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
