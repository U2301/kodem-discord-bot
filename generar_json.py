#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
import json
from pathlib import Path
from typing import List, Dict
from PyPDF2 import PdfReader

PDF_FILE = Path('Kodem base de datos .pdf')
IMG_DIR = Path('imagenes')
OUT_FILE = Path('cartas.json')

EXPANSION_HEADERS = {
    'RAICES MISTICAS': 'Raíces Místicas',
    'LA GUERRA ROJA': 'La Guerra Roja',
    'TITANES DE LA CORTEZA Y OJOS DEL OCEANO': 'Titanes de la Corteza y Ojos del Océano',
}

# ID con nombre (para capturar) y sin nombre (para lookahead)
ID_NAMED = r"(?P<id>[A-Z]{3,}[A-Z]?(?:\s*-\s*)?\d{3})"
ID_PLAIN = r"(?:[A-Z]{3,}[A-Z]?(?:\s*-\s*)?\d{3})"
BLOCK_RE = re.compile(
    rf"{ID_NAMED}\s+Nombre:\s*(?P<nombre>.+?)\s+Tipo:\s*(?P<tipo>.+?)\s+Energ[íi]a:\s*(?P<energia>.*?)(?=\s+{ID_PLAIN}|\Z)",
    re.IGNORECASE | re.DOTALL,
)

REPLACE_NOISE = [
    (re.compile(r"Asunto:\s*", re.IGNORECASE), "Tipo: "),
    (re.compile(r"Enereg[íi]a|Enreg[íi]a", re.IGNORECASE), "Energía"),
    (re.compile(r"Huúmica|Húumica", re.IGNORECASE), "Húumica"),
    (re.compile(r"Chaáktica|Cháacktica|Cháacktica", re.IGNORECASE), "Cháaktica"),
]

def normalize_id(cid: str) -> str:
    cid = cid.replace('\u2013', '-').replace('\u2014', '-')
    cid = re.sub(r"\s*\-\s*", '-', cid)
    if re.match(r"^[A-Z]{4,}\d{3}$", cid):
        cid = cid[:-3] + '-' + cid[-3:]
    return cid

def clean_field(val: str) -> str:
    val = val.strip(" :\n\t")
    # elimina artefactos tipo "4.-" al final
    val = re.sub(r"\s*\d+\.-$", "", val).strip()
    return val

def extract_cards(pdf_file: Path) -> List[Dict]:
    reader = PdfReader(str(pdf_file))
    current_expansion = None
    cards: List[Dict] = []
    for page in reader.pages:
        text = page.extract_text() or ''
        upper = text.upper()
        for raw, norm in EXPANSION_HEADERS.items():
            if raw in upper:
                current_expansion = norm
        s = ' '.join(text.split())
        for pat, repl in REPLACE_NOISE:
            s = pat.sub(repl, s)
        for m in BLOCK_RE.finditer(s):
            cid = normalize_id(m.group('id').strip())
            nombre = clean_field(m.group('nombre'))
            tipo = clean_field(m.group('tipo'))
            energia = clean_field(m.group('energia')).replace('N/A', 'Ninguna')
            cards.append({
                'id': cid,
                'nombre': nombre,
                'tipo': tipo,
                'energia': energia,
                'expansion': current_expansion or 'Desconocida',
                'imagen': None,
            })
    # De-dup
    out, seen = [], set()
    for c in cards:
        if c['id'] in seen:
            continue
        seen.add(c['id'])
        out.append(c)
    return out

def assign_images(cards) -> None:
    if not IMG_DIR.exists():
        return

    def img_sort_key(p: Path):
        # Orden numérico si encuentra número en el nombre; si no, por nombre
        m = re.search(r'(\d+)', p.stem)
        if m:
            return (0, int(m.group(1)))
        return (1, p.name.lower())

    imgs = sorted(
        [p for p in IMG_DIR.iterdir() if p.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'}],
        key=img_sort_key
    )

    for i, card in enumerate(cards):
        card['imagen'] = str(imgs[i]) if i < len(imgs) else None

def main():
    if not PDF_FILE.exists():
        raise SystemExit('No se encontró el PDF: {}'.format(PDF_FILE))
    cards = extract_cards(PDF_FILE)
    assign_images(cards)  # <- ahora solo recibe cards
    cards.sort(key=lambda x: x['id'])
    OUT_FILE.write_text(json.dumps(cards, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"Generado {OUT_FILE} con {len(cards)} cartas")

if __name__ == '__main__':
    main()
