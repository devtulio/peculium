# -*- mode: python ; coding: utf-8 -*-
"""Empacotamento do Peculium: um executável, sem instalador.

    py -m PyInstaller --clean --noconfirm Peculium.spec

A `ui/` viaja dentro do pacote e é encontrada por `peculium.raiz()`, que lê
`sys._MEIPASS` quando congelado.
"""
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

VERSAO = "0.8.0"

a = Analysis(
    ["peculium.py"],
    pathex=[],
    binaries=[],
    datas=[("ui", "ui")] + collect_data_files("webview"),
    # o pywebview escolhe o backend em tempo de execução, por import dinâmico:
    # sem declarar, o PyInstaller não enxerga nenhum deles e a janela não abre
    hiddenimports=collect_submodules("webview.platforms") + ["clr_loader"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pytest", "PIL"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name=f"Peculium v{VERSAO}",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,               # UPX é gatilho comum de falso positivo em antivírus
    runtime_tmpdir=None,
    console=False,           # é app de janela: console apareceria atrás dela
    icon="design/peculium.ico",
    version_file=None,
)
