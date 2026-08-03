"""Cofre do Peculium: o banco inteiro vive cifrado num arquivo .pec.

Formato do arquivo (DESIGN.md §3.1):

    magic 8B | versao 1B | hdr_len 2B big-endian | header JSON | nonce 12B | corpo GCM

O corpo é o dump do SQLite cifrado em AES-256-GCM sob a DEK. A DEK é gerada uma
única vez por cofre e guardada **embrulhada duas vezes** no header: pela chave
derivada da senha mestra e pela chave de recuperação (DESIGN.md §3.2).

Nada em claro toca o disco: abrir decifra para a memória via
`sqlite3.Connection.deserialize`, e gravar re-serializa e cifra.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import sqlite3
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import esquema

MAGIC = b"PECVLIVM"
VERSAO = 1
NONCE = 12
BACKUPS = 3

# ~128 MiB e ~0,5 s por tentativa. É o custo do scrypt que defende o arquivo
# roubado — o atraso entre tentativas na tela é contra dedo errado, não contra
# atacante, que ataca offline sem passar por ela (DESIGN.md §3.2).
PARAMS = {"n": 2 ** 17, "r": 8, "p": 1}
_MARGEM_MAXMEM = 2  # OpenSSL recusa se maxmem <= memória exigida pelo scrypt


class CofreError(Exception):
    pass


class SenhaIncorreta(CofreError):
    pass


class ArquivoInvalido(CofreError):
    pass


class CofreEmUso(CofreError):
    pass


# --------------------------------------------------------------------------- chaves

def _derivar(senha: str, salt: bytes, params: dict) -> bytes:
    memoria = 128 * params["n"] * params["r"] * params["p"]
    return hashlib.scrypt(senha.encode("utf-8"), salt=salt, dklen=32,
                          maxmem=memoria * _MARGEM_MAXMEM, **params)


def _embrulhar(kek: bytes, dek: bytes) -> str:
    nonce = secrets.token_bytes(NONCE)
    return base64.b64encode(nonce + AESGCM(kek).encrypt(nonce, dek, None)).decode()


def _desembrulhar(kek: bytes, blob: str) -> bytes:
    dados = base64.b64decode(blob)
    try:
        return AESGCM(kek).decrypt(dados[:NONCE], dados[NONCE:], None)
    except InvalidTag as e:
        raise SenhaIncorreta("senha ou chave de recuperação incorreta") from e


def gerar_chave_recuperacao() -> str:
    """256 bits em base32 agrupada — feita para ser impressa e digitada à mão.

    Base32 e não base64 de propósito: sem distinção de caixa e sem os pares que
    se confundem no papel."""
    bruto = base64.b32encode(secrets.token_bytes(32)).decode().rstrip("=")
    return "-".join(bruto[i:i + 4] for i in range(0, len(bruto), 4))


def _chave_recuperacao_bytes(chave: str) -> bytes:
    limpa = "".join(chave.split()).replace("-", "").upper()
    limpa += "=" * (-len(limpa) % 8)
    try:
        return base64.b32decode(limpa)
    except Exception as e:
        raise SenhaIncorreta("chave de recuperação malformada") from e


# --------------------------------------------------------------------------- trava

class _Trava:
    """Trava de instância única por cofre.

    Bloqueio do sistema operacional sobre um arquivo ao lado do .pec: se o
    processo morrer, o SO solta sozinho. Trava por PID gravado em arquivo deixaria
    resto de processo morto barrando o usuário."""

    def __init__(self, alvo: Path):
        self._caminho = alvo.with_suffix(alvo.suffix + ".lock")
        self._fd = os.open(self._caminho, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(self._fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            os.close(self._fd)
            self._fd = -1
            raise CofreEmUso(f"{alvo.name} já está aberto em outra janela") from e

    def soltar(self) -> None:
        if self._fd < 0:
            return
        try:
            if sys.platform == "win32":
                import msvcrt
                os.lseek(self._fd, 0, os.SEEK_SET)
                msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            os.close(self._fd)
            self._fd = -1


# --------------------------------------------------------------------------- arquivo

def _montar(header: dict, nonce: bytes, corpo: bytes) -> bytes:
    hdr = json.dumps(header, separators=(",", ":"), sort_keys=True).encode()
    return MAGIC + struct.pack(">BH", VERSAO, len(hdr)) + hdr + nonce + corpo


def _partir(dados: bytes) -> tuple[dict, bytes, bytes]:
    if not dados.startswith(MAGIC):
        raise ArquivoInvalido("não é um cofre do Peculium")
    versao, tam = struct.unpack(">BH", dados[8:11])
    if versao != VERSAO:
        raise ArquivoInvalido(f"cofre versão {versao}; este programa lê a {VERSAO}")
    ini = 11 + tam
    return json.loads(dados[11:ini]), dados[ini:ini + NONCE], dados[ini + NONCE:]


def _gravar_atomico(alvo: Path, dados: bytes) -> None:
    """Escreve o novo, preserva os 3 anteriores, e só então troca o corrente.

    A ordem importa: o corrente só é substituído depois que a cópia existe, então
    um crash no meio nunca deixa o usuário sem nenhum arquivo válido."""
    tmp = alvo.with_suffix(alvo.suffix + ".tmp")
    tmp.write_bytes(dados)
    if alvo.exists():
        ultimo = alvo.with_suffix(f"{alvo.suffix}.{BACKUPS}")
        ultimo.unlink(missing_ok=True)
        for i in range(BACKUPS - 1, 0, -1):
            anterior = alvo.with_suffix(f"{alvo.suffix}.{i}")
            if anterior.exists():
                os.replace(anterior, alvo.with_suffix(f"{alvo.suffix}.{i + 1}"))
        copia = alvo.with_suffix(f"{alvo.suffix}.1")
        try:
            os.link(alvo, copia)          # hardlink: não copia bytes
        except OSError:
            copia.write_bytes(alvo.read_bytes())
    os.replace(tmp, alvo)


# --------------------------------------------------------------------------- cofre

class Cofre:
    def __init__(self, caminho: Path, dek: bytes, header: dict,
                 conn: sqlite3.Connection, trava: _Trava):
        self.caminho = caminho
        self._dek = dek
        self._header = header
        self._conn = conn
        self._trava = trava
        self._aberto = True

    @property
    def conn(self) -> sqlite3.Connection:
        if not self._aberto:
            raise CofreError("cofre fechado")
        return self._conn

    def commit(self) -> None:
        """Grava o banco cifrado. Chamada a cada transação, não ao fechar:
        crash perde no máximo o último lançamento (DESIGN.md §3.3)."""
        self._conn.commit()
        nonce = secrets.token_bytes(NONCE)
        corpo = AESGCM(self._dek).encrypt(nonce, self._conn.serialize(), None)
        _gravar_atomico(self.caminho, _montar(self._header, nonce, corpo))

    def trocar_senha(self, atual: str, nova: str) -> None:
        """A DEK não muda: só o embrulho dela é refeito.

        Consequência que precisa estar clara para quem usa: **os backups
        anteriores continuam abrindo com a senha antiga**, porque carregam o
        embrulho antigo da mesma DEK."""
        salt = base64.b64decode(self._header["salt"])
        _desembrulhar(_derivar(atual, salt, self._header["kdf"]), self._header["senha"])
        salt_novo = secrets.token_bytes(16)
        self._header["salt"] = base64.b64encode(salt_novo).decode()
        self._header["senha"] = _embrulhar(
            _derivar(nova, salt_novo, self._header["kdf"]), self._dek)
        self.commit()

    def fechar(self) -> None:
        if not self._aberto:
            return
        self._aberto = False
        self._conn.close()
        self._trava.soltar()

    def __enter__(self) -> "Cofre":
        return self

    def __exit__(self, *_) -> None:
        self.fechar()


def _conectar(dump: bytes | None) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    if dump is not None:
        # O GCM garante que os bytes são os que gravamos; não garante que o que
        # gravamos era um banco são. Descobrir corrupção ao abrir é barato;
        # descobrir na véspera do DARF, não. O erro cru do SQLite não serve para
        # a tela — vira o erro do domínio.
        try:
            conn.deserialize(dump)
            estado = conn.execute("PRAGMA integrity_check").fetchone()[0]
        except sqlite3.DatabaseError as e:
            conn.close()
            raise ArquivoInvalido(f"banco ilegível dentro do cofre: {e}") from e
        if estado != "ok":
            conn.close()
            raise ArquivoInvalido(f"banco corrompido dentro do cofre: {estado}")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def criar(caminho: str | Path, senha: str, params: dict | None = None) -> tuple[Cofre, str]:
    """Cria o cofre e devolve (cofre, chave de recuperação).

    A chave de recuperação é exibida uma única vez: não fica guardada em lugar
    nenhum, só o embrulho que ela abre."""
    alvo = Path(caminho)
    if alvo.exists():
        raise CofreError(f"{alvo} já existe")
    alvo.parent.mkdir(parents=True, exist_ok=True)
    kdf = dict(params or PARAMS)
    dek = secrets.token_bytes(32)
    salt = secrets.token_bytes(16)
    recuperacao = gerar_chave_recuperacao()
    header = {
        "kdf": kdf,
        "salt": base64.b64encode(salt).decode(),
        "senha": _embrulhar(_derivar(senha, salt, kdf), dek),
        "recuperacao": _embrulhar(
            hashlib.sha256(_chave_recuperacao_bytes(recuperacao)).digest(), dek),
        "criado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    trava = _Trava(alvo)
    conn = _conectar(None)
    esquema.aplicar(conn)
    cofre = Cofre(alvo, dek, header, conn, trava)
    try:
        cofre.commit()
    except Exception:
        cofre.fechar()
        raise
    return cofre, recuperacao


def _abrir(caminho: str | Path, kek_de: callable, embrulho: str) -> Cofre:
    alvo = Path(caminho)
    header, nonce, corpo = _partir(alvo.read_bytes())
    dek = _desembrulhar(kek_de(header), header[embrulho])
    try:
        dump = AESGCM(dek).decrypt(nonce, corpo, None)
    except InvalidTag as e:
        raise ArquivoInvalido("cofre corrompido ou adulterado") from e
    trava = _Trava(alvo)
    try:
        return Cofre(alvo, dek, header, _conectar(dump), trava)
    except Exception:
        trava.soltar()
        raise


def abrir(caminho: str | Path, senha: str) -> Cofre:
    return _abrir(caminho,
                  lambda h: _derivar(senha, base64.b64decode(h["salt"]), h["kdf"]),
                  "senha")


def abrir_com_recuperacao(caminho: str | Path, chave: str) -> Cofre:
    return _abrir(caminho,
                  lambda _: hashlib.sha256(_chave_recuperacao_bytes(chave)).digest(),
                  "recuperacao")
