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
    cid = cid.replace('–', '-').replace('—', '-')
    cid = re.sub(r"\s*\-\s*", '-', cid)
    if re.match(r"^[A-Z]{4,}\d{3}$", cid):
        cid = cid[:-3] + '-' + cid[-3:]
    return cid


def clean_field(val: str) -> str:
    val = val.strip(" :\n\t")
    # elimina artefactos como '21.-' pegados al final
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
            energia = re.sub(r'\s\d+\.-', '', energia).strip()
            cards.append({
                'id': cid,
                'nombre': nombre,
                'tipo': tipo,
                'energia': energia,
                'expansion': current_expansion or 'Desconocida',
                'imagen': None,
            })
    out, seen = [], set()
    for c in cards:
        if c['id'] in seen:
            continue
        seen.add(c['id'])
        out.append(c)
    return out


def assign_images(cards, img_dir: Path) -> None:
    if not img_dir.exists():
        return

    def img_sort_key(p: Path):
        # Extrae el primer número en el nombre (sin extensión)
        import re
        m = re.search(r'(\d+)', p.stem)
        if m:
            return (0, int(m.group(1)))  # primero los que tienen número, por ese número
        return (1, p.name.lower())       # después, sin número, por nombre

    imgs = sorted(
        [p for p in img_dir.iterdir() if p.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'}],
        key=img_sort_key
    )

    for i, card in enumerate(cards):
        card['imagen'] = str(imgs[i]) if i < len(imgs) else None


def main():
    if not PDF_FILE.exists():
        raise SystemExit('No se encontró el PDF')
    cards = extract_cards(PDF_FILE)
    assign_images(cards)
    cards.sort(key=lambda x: x['id'])
    OUT_FILE.write_text(json.dumps(cards, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"Generado {OUT_FILE} con {len(cards)} cartas")

if __name__ == '__main__':
    main()
