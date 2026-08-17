from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.pdf_service import build_order_pdf


def sample_order() -> dict:
    items = [
        {'ref': '099', 'name': 'Soquete invisível senhora', 'color': 'PRETO', 'size': '30-35', 'quantity': 12, 'unitPrice': '1.25', 'lineTotal': '15.00'},
        {'ref': '2145', 'name': 'Lycra seda 15 DEN - embalagem de 2 pares', 'color': 'MUSKADE', 'size': 'Único', 'quantity': 24, 'unitPrice': '0.79', 'lineTotal': '18.96'},
        {'ref': '4230', 'name': 'Meia térmica confortável para homem', 'color': 'MARINHO', 'size': 'L/XL', 'quantity': 12, 'unitPrice': '3.45', 'lineTotal': '41.40'},
        {'ref': '6002', 'name': 'Peúga invisível homem', 'color': 'BRANCO', 'size': '40-45', 'quantity': 12, 'unitPrice': '1.50', 'lineTotal': '18.00'},
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
        'items': items,
        'lines': len(items),
        'units': sum(item['quantity'] for item in items),
        'subtotal': '93.36',
        'total': '93.36',
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
