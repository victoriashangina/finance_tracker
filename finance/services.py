import calendar
import random
from datetime import date, timedelta
from decimal import Decimal
from django.db.models import Sum, Q
from django.utils import timezone
from .models import Account, Category, Transaction

CATEGORIES = [
    ('Продукты', '#f59e0b', ['продукт', 'пятероч', 'пятёроч', 'магнит', 'вкусвилл', 'перекрест', 'перекрёст']),
    ('Кафе и рестораны', '#ed729c', ['кофе', 'кафе', 'ресторан', 'coffee', 'пекарня']),
    ('Транспорт', '#6c6ce5', ['такси', 'метро', 'транспорт', 'бензин', 'проезд']),
    ('Покупки', '#5ea5e2', ['ozon', 'wildberries', 'магазин', 'одежд', 'книг']),
    ('Дом', '#6aa89a', ['жкх', 'аренда', 'интернет', 'квартир']),
    ('Здоровье', '#eb8961', ['аптек', 'врач', 'клиник', 'спорт']),
    ('Подписки', '#9d7ee9', ['подписк', 'музык', 'кино', 'связь']),
    ('Зарплата', '#22a67b', ['зарплата', 'аванс']),
    ('Другое', '#99a1b2', []),
]


def ensure_categories(user):
    return {name: Category.objects.get_or_create(owner=user, name=name, defaults={'color': color})[0]
            for name, color, _ in CATEGORIES}


def guess_category(description, user, categories=None):
    categories = categories or ensure_categories(user)
    text = description.lower()
    for name, _, words in CATEGORIES:
        if any(word in text for word in words):
            return categories[name]
    return categories['Другое']


def money_summary(qs):
    values = qs.aggregate(expense=Sum('amount', filter=Q(kind='expense')),
                          income=Sum('amount', filter=Q(kind='income')),
                          refunds=Sum('amount', filter=Q(kind='refund')))
    values = {k: v or Decimal('0') for k, v in values.items()}
    values['net_expense'] = values['expense'] - values['refunds']
    values['difference'] = values['income'] - values['net_expense']
    return values


def category_summary(qs):
    # Donut and bars show gross purchases; refunds are displayed separately.
    data = list(qs.filter(kind='expense').values('category__name', 'category__color').annotate(total=Sum('amount')).order_by('-total'))
    total = sum(x['total'] for x in data) or Decimal('1')
    for row in data:
        row['name'] = row['category__name'] or 'Без категории'
        row['color'] = row['category__color'] or '#99a1b2'
        row['percent'] = float(row['total'] / total * 100)
    cursor, segments = 0, []
    for row in data:
        segments.append(f"{row['color']} {cursor:.2f}% {cursor + row['percent']:.2f}%")
        cursor += row['percent']
    return data, ','.join(segments) or '#eaeaf2 0% 100%'


def seed_demo(user):
    if Account.objects.filter(owner=user).exists():
        return False
    cats = ensure_categories(user)
    a = Account.objects.create(owner=user, name='На каждый день', bank='Банк А · демо', last_four='4242', opening_balance=28400, color='indigo')
    b = Account.objects.create(owner=user, name='Покупки и подписки', bank='Банк Б · демо', last_four='8080', opening_balance=18000, color='dark')
    c = Account.objects.create(owner=user, name='Наличные', bank='Кошелёк', opening_balance=7000, color='mint')
    today = timezone.localdate()
    rng = random.Random(42)
    labels = [('Продукты', 'ВкусВилл', 1350), ('Кафе и рестораны', 'Кофейня у дома', 490),
              ('Транспорт', 'Такси', 380), ('Покупки', 'Магазин книг', 1600),
              ('Здоровье', 'Аптека', 740), ('Подписки', 'Музыка · подписка', 299), ('Дом', 'Интернет', 650)]
    for delta in range(65, -1, -2):
        name, desc, amount = rng.choice(labels)
        Transaction.objects.create(account=rng.choice([a, a, b, c]), category=cats[name],
            date=today - timedelta(days=delta), description=desc, amount=amount + rng.randint(0, 150), kind='expense')
    for months in range(3):
        y, m = today.year, today.month - months
        if m < 1:
            y, m = y - 1, m + 12
        day = min(5, today.day) if months == 0 else 5
        Transaction.objects.create(account=a, category=cats['Зарплата'], date=date(y, m, day), description='Зарплата · демо', amount=85000, kind='income')
    Transaction.objects.create(account=b, category=cats['Покупки'], date=today, description='Возврат заказа · демо', amount=990, kind='refund')
    return True
