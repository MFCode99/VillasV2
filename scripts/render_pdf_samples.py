from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.pdf_service import build_order_pdf


def sample_order() -> dict:
    items = [
        {'ref': '2145', 'name': 'Mini meia lycra seda 15 DEN', 'color': 'MUSKADE', 'size': 'Único', 'quantity': 24, 'unitPrice': '0.79', 'lineTotal': '18.96', 'categoryLabel': 'Mini meia', 'categorySortOrder': 20, 'productSortOrder': 1},
        {'ref': '099', 'name': 'Soquete invisível senhora', 'color': 'PRETO', 'size': '30-35', 'quantity': 12, 'unitPrice': '1.25', 'lineTotal': '15.00', 'categoryLabel': 'Soquetes', 'categorySortOrder': 10, 'productSortOrder': 1},
        {'ref': '2145', 'name': 'Mini meia lycra seda 15 DEN', 'color': 'PRETO', 'size': 'Único', 'quantity': 12, 'unitPrice': '0.79', 'lineTotal': '9.48', 'categoryLabel': 'Mini meia', 'categorySortOrder': 20, 'productSortOrder': 1},
        {'ref': '4424a', 'name': 'Collant criança - tamanho 8', 'color': 'MARINHO', 'size': '8', 'quantity': 12, 'unitPrice': '2.00', 'lineTotal': '24.00', 'categoryLabel': 'Collants', 'categorySortOrder': 30, 'productSortOrder': 1},
        {'ref': '4424b', 'name': 'Collant criança - tamanho 12', 'color': 'BRANCO', 'size': '12', 'quantity': 12, 'unitPrice': '2.00', 'lineTotal': '24.00', 'categoryLabel': 'Collants', 'categorySortOrder': 30, 'productSortOrder': 2},
    ]
    return {
        'id': 42,
        'publicNumber': 'VLS-2026-000042',
        'createdAt': datetime(2026, 8, 16, 15, 30),
        'orderStatus': 'confirmed',
        'customerName': 'Cliente Demonstração',
        'customerCompany': 'Loja Exemplo, Lda.',
        'customerNif': '500 000 000',
        'customerEmail': 'compras@exemplo.pt',
        'customerPhone': '+351 210 000 000',
        'customerAddressLine1': 'Avenida do Comércio, 125',
        'customerAddressLine2': 'Armazém B',
        'customerPostalCode': '1000-100',
        'customerCity': 'Lisboa',
        'customerCountry': 'Portugal',
        'customerCarrier': 'Transportes Exemplo, Lda.',
        'items': items,
        'lines': len(items),
        'units': sum(item['quantity'] for item in items),
        'subtotal': '91.44',
        'total': '91.44',
        'notes': 'Entregar durante o período da manhã.\nConfirmar disponibilidade antes da expedição.',
    }


def main() -> None:
    output = Path('output/pdf')
    output.mkdir(parents=True, exist_ok=True)
    order = sample_order()
    (output / 'villas-encomenda-com-precos.pdf').write_bytes(build_order_pdf(order))
    (output / 'villas-encomenda-sem-precos.pdf').write_bytes(build_order_pdf(order, hide_prices=True))


if __name__ == '__main__':
    main()
