# -*- mode: python ; coding: utf-8 -*-
"""Empacotamento do Peculium: um executável, sem instalador.

    py -m PyInstaller --clean --noconfirm Peculium.spec

A `ui/` viaja dentro do pacote e é encontrada por `peculium.raiz()`, que lê
`sys._MEIPASS` quando congelado.
"""
from glob import glob
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

VERSAO = "0.11.1"

# Recurso de versão do Windows. Binário sem assinatura E sem metadado não tem
# nada por onde ganhar reputação: o Explorer mostra "Publicador desconhecido" e
# nem o nome do programa. É o passo mais barato contra o Smart App Control, e
# não substitui assinatura — só deixa de piorar.
_v = tuple(int(p) for p in VERSAO.split(".")) + (0,)
Path("versao.txt").write_text(f"""\
VSVersionInfo(
  ffi=FixedFileInfo(filevers={_v}, prodvers={_v}, mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
        StringStruct('CompanyName', 'Peculium'),
        StringStruct('FileDescription', 'Peculium — gerenciador de investimentos'),
        StringStruct('FileVersion', '{VERSAO}'),
        StringStruct('InternalName', 'Peculium'),
        StringStruct('LegalCopyright', 'Licenca MIT'),
        StringStruct('OriginalFilename', 'Peculium.exe'),
        StringStruct('ProductName', 'Peculium'),
        StringStruct('ProductVersion', '{VERSAO}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""", encoding="utf-8")

a = Analysis(
    ["peculium.py"],
    pathex=[],
    binaries=[],
    # `mock.js` fica de fora: é a ponte falsa dos testes de tela, e uma fonte de
    # dado inventado não tem o que fazer dentro do binário publicado.
    datas=[(p, "ui") for p in glob("ui/*") if not p.endswith("mock.js")] \
          + collect_data_files("webview"),
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
    # `version`, não `version_file`: o EXE lê os extras de **kwargs e ignora em
    # SILÊNCIO o nome que não conhece. O `version_file=None` que estava aqui
    # antes nunca foi lido por ninguém, e a primeira tentativa de arrumar isto
    # gerou um binário com todos os campos vazios sem uma linha de aviso no log.
    # O que denuncia é o "Copying version information to EXE" faltando.
    version="versao.txt",
)
