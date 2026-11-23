"""Fonts you can pick for the name on a certificate.

Every file ships in static/certificates/fonts (free licences: SIL OFL, GUST/TeX Gyre,
Liberation, DejaVu) so the server and the browser preview use the same font.
"""

FONTS = [
    ("cardo", "Cardo Bold", "Serif", "cardo.ttf"),
    ("crimson", "Crimson Text Bold", "Serif", "crimson.ttf"),
    ("caladea", "Caladea Bold", "Serif", "caladea.ttf"),
    ("dejavu-serif", "DejaVu Serif Bold", "Serif", "dejavu-serif.ttf"),
    ("liberation-serif", "Liberation Serif Bold", "Serif", "liberation-serif.ttf"),
    ("termes", "TeX Gyre Termes Bold", "Serif", "termes.otf"),
    ("pagella", "TeX Gyre Pagella Bold", "Serif", "pagella.otf"),
    ("bonum", "TeX Gyre Bonum Bold", "Serif", "bonum.otf"),
    ("schola", "TeX Gyre Schola Bold", "Serif", "schola.otf"),
    ("poppins", "Poppins Bold", "Sans", "poppins.ttf"),
    ("poppins-medium", "Poppins Medium", "Sans", "poppins-medium.ttf"),
    ("fira-sans", "Fira Sans Bold", "Sans", "fira-sans.ttf"),
    ("fira-sans-medium", "Fira Sans Medium", "Sans", "fira-sans-medium.ttf"),
    ("carlito", "Carlito Bold", "Sans", "carlito.ttf"),
    ("liberation-sans", "Liberation Sans Bold", "Sans", "liberation-sans.ttf"),
    ("dejavu-sans", "DejaVu Sans Bold", "Sans", "dejavu-sans.ttf"),
    ("inter", "Inter Bold", "Sans", "inter.otf"),
    ("heros", "TeX Gyre Heros Bold", "Sans", "heros.otf"),
    ("adventor", "TeX Gyre Adventor Bold", "Sans", "adventor.otf"),
    ("anton", "Anton", "Display", "anton.ttf"),
    ("archivo-black", "Archivo Black", "Display", "archivo-black.ttf"),
    ("chorus", "TeX Gyre Chorus Italic", "Script", "chorus.otf"),
    ("cardo-italic", "Cardo Italic", "Script", "cardo-italic.ttf"),
    ("crimson-italic", "Crimson Text Bold Italic", "Script", "crimson-italic.ttf"),
    ("caladea-italic", "Caladea Bold Italic", "Script", "caladea-italic.ttf"),
    ("dejavu-serif-italic", "DejaVu Serif Italic", "Script", "dejavu-serif-italic.ttf"),
    ("liberation-serif-italic", "Liberation Serif Italic", "Script", "liberation-serif-italic.ttf"),
    ("poppins-italic", "Poppins Italic", "Script", "poppins-italic.ttf"),
    ("comic-relief", "Comic Relief Bold", "Fun", "comic-relief.ttf"),
    ("anonymous-pro", "Anonymous Pro Bold", "Mono", "anonymous-pro.ttf"),
    ("liberation-mono", "Liberation Mono Bold", "Mono", "liberation-mono.ttf"),
    ("dejavu-mono", "DejaVu Sans Mono Bold", "Mono", "dejavu-mono.ttf"),
    ("cursor", "TeX Gyre Cursor Bold", "Mono", "cursor.otf"),
]

FONT_FILES = {key: fname for key, _label, _cat, fname in FONTS}


def font_catalog():
    """List of dicts for the picker template."""
    return [{"key": k, "label": l, "category": c, "file": f} for k, l, c, f in FONTS]
