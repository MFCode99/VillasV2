from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.pdf_service import build_order_pdf


def utilities_order() -> dict:
    items = [
        {'ref': 'LR6-AA', 'name': 'Pilha alcalina AA', 'quantity': 48, 'unitPrice': '1.250', 'lineTotal': '60.00', 'categoryLabel': 'Alcalinas', 'categorySortOrder': 11, 'productSortOrder': 1, 'catalogSlug': 'interpilhas'},
        {'ref': 'CR2032', 'name': 'Pilha de lítio CR2032', 'quantity': 100, 'unitPrice': '0.850', 'lineTotal': '85.00', 'categoryLabel': 'Lítio', 'categorySortOrder': 13, 'productSortOrder': 1, 'catalogSlug': 'interpilhas'},
        {'ref': 'AREON-MON', 'name': 'Ambientador Mon Areon', 'quantity': 36, 'unitPrice': '2.350', 'lineTotal': '84.60', 'categoryLabel': 'Mon Areon', 'categorySortOrder': 21, 'productSortOrder': 1, 'catalogSlug': 'interpilhas'},
        {'ref': 'GOMA-95', 'name': 'Cola GomaGom 95', 'quantity': 30, 'unitPrice': '2.400', 'lineTotal': '72.00', 'categoryLabel': 'Colas instantâneas', 'categorySortOrder': 31, 'productSortOrder': 1, 'catalogSlug': 'interpilhas'},
    ]
    return {
        'id': 101,
        'publicNumber': 'VLS-2026-000101',
        'catalogSlug': 'interpilhas',
        'createdAt': datetime(2026, 10, 30, 10, 30),
        'orderStatus': 'confirmed',
        'customerName': 'Cliente Demonstração',
        'customerCompany': 'Loja Exemplo, Lda.',
        'customerNif': '500 000 000',
        'customerEmail': 'compras@exemplo.pt',
        'customerPhone': '+351 210 000 000',
        'customerAddressLine1': 'Avenida do Comércio, 125',
        'customerPostalCode': '1000-100',
        'customerCity': 'Lisboa',
        'customerCountry': 'Portugal',
        'customerCarrier': 'Transportes Exemplo, Lda.',
        'items': items,
        'lines': len(items),
        'units': sum(item['quantity'] for item in items),
        'subtotal': '301.60',
        'total': '301.60',
    }


def main() -> None:
    output = Path('output/pdf')
    output.mkdir(parents=True, exist_ok=True)
    order = utilities_order()
    (output / 'vitor-gouveia-utilidades-com-precos.pdf').write_bytes(build_order_pdf(order))
    (output / 'vitor-gouveia-utilidades-sem-precos.pdf').write_bytes(build_order_pdf(order, hide_prices=True))


if __name__ == '__main__':
    main()
