#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
import json
from pathlib import Path
from typing import List, Dict, Tuple
from PyPDF2 import PdfReader

PDF_FILE = Path('Kodem base de datos .pdf')
IMG_DIR = Path('imagenes')
OUT_FILE = Path('cartas.json')

# Encabezados que aparecen en el PDF (en MAYÚSCULAS)
EXPANSION_HEADERS = {
    'RAICES MISTICAS': 'Raíces Místicas',
    'LA GUERRA ROJA': 'La Guerra Roja',
    'TITANES DE LA CORTEZA Y OJOS DEL OCEANO': 'Titanes de la Corteza y Ojos del Océano',
}

# Patrón de bloque: ID + Nombre + Tipo + Energía
# Lo ejecutaremos sobre TODO el documento ya normalizado,
# no por páginas, para capturar bloques que cruzan saltos de página.
ID_NAMED = r"(?P<id>[A-Z]{3,}[A-Z]?(?:\s*-\s*)?\d{3})"
ID_PLAIN = r"(?:[A-Z]{3,}[A-Z]?(?:\s*-\s*)?\d{3})"
BLOCK_RE = re.compile(
    rf"{ID_NAMED}\s+Nombre:\s*(?P<nombre>.+?)\s+Tipo:\s*(?P<tipo>.+?)\s+Energ[íi]a:\s*(?P<energia>.*?)(?=\s+{ID_PLAIN}|\Z)",
    re.IGNORECASE | re.DOTALL,
)

# Normalizaciones de OCR
REPLACE_NOISE = [
    (re.compile(r"Asunto:\s*", re.IGNORECASE), "Tipo: "),
    (re.compile(r"Enereg[íi]a|Enreg[íi]a", re.IGNORECASE), "Energía"),
    (re.compile(r"Huúmica|Húumica", re.IGNORECASE), "Húumica"),
    (re.compile(r"Chaáktica|Cháacktica|Cháacktica", re.IGNORECASE), "Cháaktica"),
    (re.compile(r"\s+", re.MULTILINE), " "),  # colapsa espacios/saltos
]

def read_full_pdf_text(pdf_file: Path) -> str:
    reader = PdfReader(str(pdf_file))
    # Une todo el documento en un solo string
    parts = []
    for page in reader.pages:
        try:
            t = page.extract_text() or ''
        except Exception:
            t = ''
        parts.append(t)
    s = " ".join(parts)
    # Normaliza ruidos
    for pat, repl in REPLACE_NOISE:
        s = pat.sub(repl, s)
    return s.strip()

def normalize_id(cid: str) -> str:
    cid = cid.replace('\u2013', '-').replace('\u2014', '-')
    cid = re.sub(r"\s*\-\s*", '-', cid)
    # Inserta guión si falta (LGRO012 -> LGRO-012)
    if re.match(r"^[A-Z]{4,}\d{3}$", cid):
        cid = cid[:-3] + '-' + cid[-3:]
    return cid

def clean_field(val: str) -> str:
    val = val.strip(" :\n\t")
    # elimina artefactos tipo "4.-" al final
    val = re.sub(r"\s*\d+\.-$", "", val).strip()
    return val

def find_expansion_positions(s: str) -> List[Tuple[int, str]]:
    # Devuelve [(posicion_en_texto, nombre_normalizado)]
    out = []
    upper = s.upper()
    for raw, norm in EXPANSION_HEADERS.items():
        start = 0
        while True:
            idx = upper.find(raw, start)
            if idx == -1:
                break
            out.append((idx, norm))
            start = idx + 1
    out.sort(key=lambda x: x[0])
    return out

def extract_cards_with_expansions(s: str) -> List[Dict]:
    expansions = find_expansion_positions(s)  # lista ordenada por posición
    cards: List[Dict] = []

    # Recorremos los matches en orden; para cada carta, buscamos
    # el encabezado de expansión más cercano por detrás (posición <= inicio del match)
    ei = 0  # índice de expansión
    for m in BLOCK_RE.finditer(s):
        start = m.start()
        # avanza el puntero de expansiones mientras su pos <= inicio del match
        while ei + 1 < len(expansions) and expansions[ei + 1][0] <= start:
            ei += 1
        current_expansion = expansions[ei][1] if expansions else 'Desconocida'

        cid = normalize_id(m.group('id').strip())
        nombre = clean_field(m.group('nombre'))
        tipo = clean_field(m.group('tipo'))
        energia = clean_field(m.group('energia')).replace('N/A', 'Ninguna')

        cards.append({
            'id': cid,
            'nombre': nombre,
            'tipo': tipo,
            'energia': energia,
            'expansion': current_expansion,
            'imagen': None,
        })

    # De-dup por id, manteniendo el primero
    out, seen = [], set()
    for c in cards:
        if c['id'] in seen:
            continue
        seen.add(c['id'])
        out.append(c)
    return out

def assign_images(cards: List[Dict]) -> None:
    """
    Asigna imagenes/imagenN.* a la N-ésima carta en orden de aparición del PDF.
    """
    if not IMG_DIR.exists():
        return

    valid_ext = {'.jpg', '.jpeg', '.png', '.webp'}
    index_to_path = {}
    for p in IMG_DIR.iterdir():
        if p.suffix.lower() not in valid_ext:
            continue
        m = re.search(r'(\d+)', p.stem)
        if not m:
            continue
        n = int(m.group(1))
        # Si existen duplicados de N, el último gana (puedes ajustar si prefieres)
        index_to_path[n] = p

    for i, card in enumerate(cards, start=1):
        card['imagen'] = str(index_to_path[i]) if i in index_to_path else None

def main():
    if not PDF_FILE.exists():
        raise SystemExit(f'No se encontró el PDF: {PDF_FILE}')

    # 1) Leer texto global (para no perder cartas que cruzan páginas)
    s = read_full_pdf_text(PDF_FILE)

    # 2) Extraer cartas en el orden en que aparecen en el documento
    cards = extract_cards_with_expansions(s)

    # 3) Asignar imagen por índice (1→imagen1.jpeg, 2→imagen2.jpeg, …)
    assign_images(cards)

    # 4) (Opcional) Ordenar por ID para el archivo final (la imagen ya quedó pegada)
    cards.sort(key=lambda x: x['id'])

    OUT_FILE.write_text(json.dumps(cards, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"Generado {OUT_FILE} con {len(cards)} cartas")

if __name__ == '__main__':
    main()
