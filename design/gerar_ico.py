# Gera peculium.ico multi-frame a partir da geometria E3 (tabulae ligatae).
# Frames 256/128/64/48/32 usam a arte completa (icone-e3.svg); 24/16 usam a arte
# dedicada de campo claro (icone-e3-16.svg) — a arte grande é escura e some na
# barra de tarefas escura do Windows quando reduzida.
# Receita herdada do Licitarium: desenhar a 1024px e reduzir com LANCZOS; frames
# ordenados do maior para o menor; fundo transparente.
from PIL import Image, ImageDraw, ImageFilter, ImageFont

PURPURA = (99, 35, 76, 255)       # #63234c
PURPURA_ESC = (74, 26, 58, 255)   # #4a1a3a
PURPURA_CLA = (141, 63, 114, 255) # #8d3f72
LAMINA = (78, 27, 61, 255)        # #4e1b3d — purpura_esc a 85% sobre purpura
RESERVA = (83, 48, 54, 255)       # #533036 — cera_cla a 55% sobre purpura
LINUM = (207, 196, 170, 255)      # #cfc4aa
AURUM = (176, 141, 62, 255)       # #b08d3e
OSSO = (233, 225, 208, 255)       # #e9e1d0
F = 16                            # supersample: viewBox 64 -> canvas 1024


def _canvas():
    img = Image.new("RGBA", (64 * F, 64 * F), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _box(x, y, w, h):
    return [x * F, y * F, (x + w) * F, (y + h) * F]


def arte_completa():
    img, d = _canvas()
    # capa de madeira do díptico fechado
    d.rounded_rectangle(_box(11, 8, 42, 44), radius=2.5 * F, fill=PURPURA,
                        outline=PURPURA_CLA, width=round(1 * F))
    # margo: o bordo elevado que protegia a cera com as tabuinhas fechadas
    d.rounded_rectangle(_box(15, 12, 34, 36), radius=1 * F, fill=RESERVA)
    # corte das lâminas: o que faz ler "pilha de tabuinhas", não "caixa".
    # Encostadas na capa — com folga, lêem como sombra solta.
    for i, y in enumerate((51.4, 54.2)):
        d.rounded_rectangle(_box(12 + i, y, 40 - i * 2, 2.4), radius=.9 * F,
                            fill=LAMINA if i == 0 else PURPURA_CLA)
    # linum: o cordão dava UMA volta na peça — cruz lê embrulho de presente
    d.rectangle(_box(11, 27.5, 42, 4), fill=LINUM)
    # sigillum sobre o nó
    d.ellipse(_box(23, 20.5, 18, 18), fill=PURPURA_ESC, outline=AURUM,
              width=round(1.4 * F))
    font = ImageFont.truetype("C:/Windows/Fonts/georgiab.ttf", 12 * F)
    d.text((32 * F, 35 * F), "P", font=font, fill=OSSO, anchor="ms")
    return img


def arte_16px():
    img, d = _canvas()
    # Capa + linum + sigillum são três elementos e a 16px viram um losango.
    # Sobra a capa e a letra — a mesma saída do L do Licitarium. Capa escura com
    # letra clara serve às duas barras de tarefas: a massa aparece na clara, a
    # letra aparece na escura.
    d.rounded_rectangle(_box(5, 3, 54, 54), radius=5 * F, fill=PURPURA)
    d.rounded_rectangle(_box(9, 58, 46, 3.6), radius=1.6 * F, fill=PURPURA)
    font = ImageFont.truetype("C:/Windows/Fonts/georgiab.ttf", 40 * F)
    # branco puro: a 16px o tom creme não sobrevive e cada nível de contraste conta
    d.text((32 * F, 47 * F), "P", font=font, fill=(255, 255, 255, 255), anchor="ms")
    return img


def prova_barra(frames):
    """Folha de prova: os frames reais sobre barra de tarefas escura e clara.
    O ícone vive ali, não no preview ampliado — é onde a decisão se confere."""
    esc, cla = (31, 31, 31, 255), (243, 243, 243, 255)
    larg, alt = 560, 240   # a faixa precisa caber o 48 ampliado 2x (96px)
    folha = Image.new("RGBA", (larg, alt), (255, 255, 255, 255))
    for faixa, cor in enumerate((esc, cla)):
        fundo = Image.new("RGBA", (larg, alt // 2), cor)
        x = 16
        for s, im in frames:
            if s > 48:
                continue
            fundo.alpha_composite(im, (x, (alt // 2 - s) // 2))
            fundo.alpha_composite(im.resize((s * 2, s * 2), Image.NEAREST),
                                  (x + s + 8, (alt // 2 - s * 2) // 2))
            x += s * 3 + 40
        folha.alpha_composite(fundo, (0, faixa * (alt // 2)))
    folha.save("icone-prova-barra.png")


def main():
    completa, dedicada = arte_completa(), arte_16px()
    # corte em 32 (e não em 24, como no Licitarium): o sigillum é detalhe fino e
    # o frame de 32 já sai borrado com a arte completa — conferido na folha de prova
    frames = [(s, completa) for s in (256, 128, 64, 48)] + \
             [(s, dedicada) for s in (32, 24, 16)]
    imgs = []
    for s, art in frames:
        im = art.resize((s, s), Image.LANCZOS)
        if s <= 32:  # frames pequenos: recuperar nitidez perdida na redução
            im = im.filter(ImageFilter.SHARPEN)
        imgs.append(im)
    imgs[0].save("peculium.ico", format="ICO", append_images=imgs[1:])
    completa.resize((256, 256), Image.LANCZOS).save("icone-preview-256.png")
    dedicada.resize((16, 16), Image.LANCZOS).filter(ImageFilter.SHARPEN) \
            .resize((128, 128), Image.NEAREST) \
            .save("icone-preview-16x.png")   # 16px ampliado 8x p/ inspeção
    completa.resize((48, 48), Image.LANCZOS).resize((192, 192), Image.NEAREST) \
            .save("icone-preview-48x.png")   # 48px ampliado 4x p/ inspeção
    prova_barra(list(zip((s for s, _ in frames), imgs)))
    print("frames:", Image.open("peculium.ico").info.get("sizes"))


if __name__ == "__main__":
    main()
