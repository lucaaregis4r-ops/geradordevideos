"""Conservative lexical suggestions; never silently broaden the visual brief."""
import re

ABSTRACT = re.compile(r'\b(economy|market|wealth|value|capitalism|supply chain)\b', re.I)
SYNONYMS = (
    ('coffee bag', 'coffee package'), ('coffee package', 'coffee bag'),
    ('t-shirt', 'tee shirt'), ('tee shirt', 't-shirt'),
    ('price tag', 'price label'), ('grocery shelf', 'supermarket shelf'),
    ('supermarket shelf', 'grocery shelf'), ('cash register', 'checkout register'),
    ('cardboard box', 'cardboard carton'), ('cargo truck', 'freight truck'),
    ('sewing clothes', 'sewing garments'), ('ceramic cup', 'ceramic mug'),
)


def suggest_queries(queries: list[str], forbidden: list[str] | None = None) -> list[dict[str, str]]:
    existing = {q.strip().casefold() for q in queries}
    result = []
    for original in queries:
        for term, synonym in SYNONYMS:
            proposed = re.sub(r'(?<!\w)' + re.escape(term) + r'(?!\w)', synonym, original, flags=re.I).strip()
            if proposed.casefold() in existing or ABSTRACT.search(proposed):
                continue
            if any(re.search(r'(?<!\w)'+re.escape(x.strip())+r'(?!\w)', proposed, re.I)
                   for x in forbidden or [] if x.strip()):
                continue
            existing.add(proposed.casefold())
            result.append({'query': proposed, 'original': original,
                           'reason': f'Variação de vocabulário: {term} → {synonym}. Confira se representa a mesma cena.'})
    return result[:5]
