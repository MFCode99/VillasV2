from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill, Protection
from openpyxl.worksheet.datavalidation import DataValidation


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT.parents[1] / 'outputs' / '01a00c27-e93e-7651-93fd-7d9466222a2c' / 'modelo-importacao-produtos.xlsx'
STATIC = ROOT / 'app' / 'static' / 'templates' / 'modelo-importacao-produtos.xlsx'

HEADERS = [
    'Referência', 'Marca', 'Categoria', 'Subcategoria', 'Descrição', 'EAN',
    'Cx Interior', 'Cx Exterior', 'Preço Base', 'Ecovalor', 'Preço Unitário',
    'Família', 'Tipo', 'Múltiplo', 'Atalhos de quantidade', 'Cores', 'Tamanhos', 'Ativo',
]


def create_workbook() -> Workbook:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'PRODUTOS'
    sheet.append(HEADERS)
    sheet.freeze_panes = 'A2'
    sheet.auto_filter.ref = 'A1:R5001'
    sheet.row_dimensions[1].height = 28
    header_fill = PatternFill('solid', fgColor='243B53')
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = Font(color='FFFFFF', bold=True)
        cell.alignment = Alignment(vertical='center')
    widths = [18, 16, 20, 22, 44, 18, 13, 13, 14, 12, 16, 20, 16, 12, 24, 20, 20, 11]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[chr(64 + index)].width = width
    for row in range(2, 5002):
        sheet.cell(row, 9).number_format = '0.000'
        sheet.cell(row, 10).number_format = '0.000'
        sheet.cell(row, 11).number_format = '0.000'
    active_validation = DataValidation(type='list', formula1='"Sim,Não"', allow_blank=True)
    sheet.add_data_validation(active_validation)
    active_validation.add('R2:R5001')
    sheet.conditional_formatting.add('A2:R5001', FormulaRule(formula=['$A2=""'], fill=PatternFill('solid', fgColor='F7F9FC')))

    help_sheet = workbook.create_sheet('INSTRUÇÕES')
    help_sheet.sheet_view.showGridLines = False
    help_sheet.column_dimensions['A'].width = 26
    help_sheet.column_dimensions['B'].width = 92
    help_sheet['A1'] = 'Modelo de importação'
    help_sheet['A1'].font = Font(size=18, bold=True, color='243B53')
    help_sheet.merge_cells('A1:B1')
    rows = [
        ('Como usar', 'Preencha a folha PRODUTOS, mantenha os cabeçalhos e carregue o ficheiro na área Catálogos → Importar Excel.'),
        ('Obrigatórios', 'Referência, Descrição e Preço Unitário.'),
        ('Categorias', 'Categoria cria o grupo principal; Subcategoria cria o nível abaixo. Se ainda não existirem, serão criadas automaticamente.'),
        ('Preços', 'Use números sem o símbolo €. São aceites vírgula ou ponto decimal.'),
        ('Múltiplo', 'Passo mínimo usado nos controlos de quantidade. Use 1 quando não houver múltiplo.'),
        ('Atalhos', 'Quantidades separadas por vírgula, por exemplo: 12, 24, 144. Pode deixar vazio.'),
        ('Variantes', 'Cores e Tamanhos podem ser separados por vírgula. Deixe vazios quando o produto não tiver variantes.'),
        ('Ativo', 'Sim/Não. Se ficar vazio, o produto é criado como ativo.'),
        ('Exemplo', 'EXEMPLO-001 | MARCA | Pilhas | Alcalinas | Produto de exemplo | EAN | 12 | 144 | 0,500 | 0,050 | 0,550 | Família | Produto | 1 | 12, 24, 144 | cores | tamanhos | Sim'),
        ('Atualizações', 'Se a referência já existir e a opção de atualizar estiver ligada, os dados desse produto serão substituídos.'),
    ]
    for index, (title, description) in enumerate(rows, start=3):
        help_sheet.cell(index, 1, title).font = Font(bold=True, color='243B53')
        help_sheet.cell(index, 2, description).alignment = Alignment(wrap_text=True, vertical='top')
        help_sheet.row_dimensions[index].height = 34
    help_sheet.protection.sheet = True
    help_sheet.protection.password = 'modelo'
    for row in help_sheet.iter_rows():
        for cell in row:
            cell.protection = Protection(locked=True)
    workbook.active = 0
    return workbook


def main() -> None:
    workbook = create_workbook()
    for path in (OUTPUT, STATIC):
        path.parent.mkdir(parents=True, exist_ok=True)
        workbook.save(path)
        print(path)


if __name__ == '__main__':
    main()
