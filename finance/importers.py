"""Small, explicit parsers. No OCR or bank login access."""
import csv
import hashlib
import io
import re
import zipfile
from collections import Counter
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

from openpyxl import load_workbook
from pypdf import PdfReader

MAX_ROWS = 1000
ALIASES = {
    'date': ['date', 'дата', 'дата операции', 'дата платежа'],
    'description': ['description', 'описание', 'назначение платежа', 'описание операции', 'назначение'],
    'amount': ['amount', 'сумма', 'сумма операции', 'сумма в валюте счета'],
    'currency': ['currency', 'валюта', 'валюта операции'],
    'type': ['type', 'тип', 'тип операции', 'вид операции'],
    'id': ['id', 'идентификатор', 'id операции'],
}
KINDS = {'expense': 'expense', 'расход': 'expense', 'списание': 'expense',
         'income': 'income', 'доход': 'income', 'поступление': 'income',
         'refund': 'refund', 'возврат': 'refund', 'возврат покупки': 'refund',
         'transfer_in': 'transfer_in', 'перевод на счет': 'transfer_in',
         'transfer_out': 'transfer_out', 'перевод со счета': 'transfer_out'}


class ImportProblem(ValueError):
    pass


def normalized(text):
    return re.sub(r'\s+', ' ', str(text or '').strip().lower().replace('ё', 'е'))


def parse_amount(value):
    s = str(value).replace('\u00a0', '').replace(' ', '').replace('₽', '').replace('−', '-')
    if ',' in s and '.' in s:
        raise ValueError('Неоднозначная сумма: используй один десятичный разделитель.')
    number = Decimal(s.replace(',', '.'))
    if not number.is_finite() or abs(number) >= Decimal('10000000000') or not number:
        raise ValueError('Сумма должна быть ненулевой и меньше 10 миллиардов.')
    if number != number.quantize(Decimal('.01')):
        raise ValueError('В сумме допускаются только два знака после запятой.')
    return number


def parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    for fmt in ['%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y', '%d.%m.%Y %H:%M', '%d.%m.%Y %H:%M:%S']:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise ValueError('Дата должна быть ДД.ММ.ГГГГ или ГГГГ-ММ-ДД.')


def spreadsheet_rows(data, extension):
    if extension == 'xlsx':
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if sum(i.file_size for i in archive.infolist()) > 30 * 1024 * 1024:
                raise ImportProblem('Слишком большой распакованный Excel-файл.')
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True, keep_links=False)
        try:
            rows = []
            for row in wb.active.iter_rows(values_only=True):
                rows.append(list(row))
                if len(rows) > MAX_ROWS + 30:
                    raise ImportProblem('Раздели выписку на файлы до 1000 строк.')
            return rows
        finally:
            wb.close()
    for encoding in ['utf-8-sig', 'cp1251']:
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            pass
    else:
        raise ImportProblem('Не удалось прочитать кодировку CSV. Сохрани его как UTF-8.')
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=';,\t')
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    if len(rows) > MAX_ROWS + 30:
        raise ImportProblem('Раздели выписку на файлы до 1000 строк.')
    return rows


def pdf_rows(data):
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise ImportProblem('PDF защищён паролем. Экспортируй выписку без защиты.')
    if len(reader.pages) > 30:
        raise ImportProblem('PDF должен содержать не больше 30 страниц.')
    text = '\n'.join(page.extract_text() or '' for page in reader.pages)
    if not text.strip():
        raise ImportProblem('В PDF нет текста. Сканирование не поддерживается: используй CSV, XLSX или ручной ввод.')
    result = [['date', 'description', 'amount', 'currency', 'type']]
    for line in text.splitlines():
        line = line.strip()
        if not re.match(r'^(\d{2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2})', line):
            continue
        if ';' in line:
            result.append(next(csv.reader([line], delimiter=';')))
        else:
            # Single-line text statement: date description signed-amount RUB.
            m = re.match(r'^(\d{2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2})\s+(.+?)\s+([+\-−]?\d[\d \u00a0]*[.,]\d{2})\s*(RUB|RUR|₽)?$', line)
            if m:
                result.append([m[1], m[2], m[3], 'RUB', ''])
            else:
                result.append([line, '', '', '', ''])
    if len(result) == 1:
        raise ImportProblem('Структура этого PDF не распознана. Используй образец текстового PDF, CSV или XLSX.')
    if len(result) > MAX_ROWS + 1:
        raise ImportProblem('В одном файле допускается до 1000 операций.')
    return result


def parse_statement(upload):
    extension = upload.name.rsplit('.', 1)[-1].lower()
    data = upload.read(5 * 1024 * 1024 + 1)
    if len(data) > 5 * 1024 * 1024:
        raise ImportProblem('Размер файла превышает 5 МБ.')
    try:
        raw = pdf_rows(data) if extension == 'pdf' else spreadsheet_rows(data, extension)
    except ImportProblem:
        raise
    except Exception as exc:
        raise ImportProblem('Файл повреждён или не соответствует выбранному формату.') from exc
    mapping, header = {}, None
    for i, row in enumerate(raw[:30]):
        mapping = {key: n for n, value in enumerate(row)
                   for key, names in ALIASES.items() if normalized(value) in names}
        if {'date', 'description', 'amount'} <= set(mapping):
            header = i
            break
    if header is None:
        raise ImportProblem('Нужны колонки «Дата», «Описание», «Сумма». Скачай пример на странице импорта.')
    rows, errors, occurrences = [], [], Counter()
    for n, cells in enumerate(raw[header + 1:], header + 2):
        if not any(v is not None and str(v).strip() for v in cells):
            continue
        record = {key: cells[index] if index < len(cells) else '' for key, index in mapping.items()}
        try:
            day = parse_date(record.get('date'))
            description = str(record.get('description') or '').strip()
            if not description or len(description) > 250:
                raise ValueError('Описание должно содержать от 1 до 250 символов.')
            currency = normalized(record.get('currency'))
            if currency not in ['', 'rub', 'rur', 'руб', 'руб.', '₽']:
                raise ValueError('Поддерживаются только рубли (RUB).')
            amount = parse_amount(record.get('amount'))
            kind_text = normalized(record.get('type'))
            if kind_text and kind_text not in KINDS:
                raise ValueError('Неизвестный тип операции.')
            kind = KINDS.get(kind_text, 'expense' if amount < 0 else 'income')
            raw_key = '|'.join([day.isoformat(), normalized(description), f'{abs(amount):.2f}', kind])
            external_id = str(record.get('id') or '').strip()
            if external_id:
                raw_key = 'external:' + external_id
            signature = hashlib.sha256(raw_key.encode()).hexdigest()
            occurrences[signature] += 1
            # Distinct identical purchases inside the same file remain distinct.
            dedup_key = f'{signature}:{occurrences[signature]}'
            rows.append({'line': n, 'date': day.isoformat(), 'description': description,
                         'amount': f'{abs(amount):.2f}', 'kind': kind, 'dedup_key': dedup_key})
        except (ValueError, InvalidOperation, TypeError) as exc:
            errors.append({'line': n, 'message': str(exc) or 'Некорректная сумма или дата.'})
    if not rows and not errors:
        raise ImportProblem('В файле нет операций.')
    return rows, errors
