import uuid
from decimal import Decimal
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q, Sum, Case, When, F, DecimalField
from django.db.models.functions import Lower


class User(AbstractUser):
    email = models.EmailField('Электронная почта', unique=True)

    class Meta:
        constraints = [models.UniqueConstraint(Lower('email'), name='unique_email_casefold')]


class LoginAttempt(models.Model):
    key = models.CharField(max_length=64, unique=True)
    failures = models.PositiveIntegerField(default=0)
    window_start = models.DateTimeField()


class Account(models.Model):
    COLORS = [('indigo', 'Индиго'), ('mint', 'Мята'), ('dark', 'Графит'), ('rose', 'Розовый')]
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField('Название счёта', max_length=80)
    bank = models.CharField('Банк или источник', max_length=80)
    last_four = models.CharField('Последние 4 цифры карты', max_length=4, blank=True,
                                validators=[RegexValidator(r'^\d{4}$', 'Укажи ровно 4 цифры или оставь поле пустым.')])
    opening_balance = models.DecimalField('Начальный баланс, ₽', max_digits=14, decimal_places=2, default=0)
    color = models.CharField('Цвет карточки', choices=COLORS, default='indigo', max_length=12)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.bank} · {self.name}'

    @property
    def balance(self):
        net = self.entries.aggregate(total=Sum(Case(
            When(kind__in=['expense', 'transfer_out'], then=-F('amount')),
            default=F('amount'), output_field=DecimalField())))['total'] or Decimal('0')
        return self.opening_balance + net


class Category(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField('Название', max_length=60)
    color = models.CharField('Цвет', max_length=7, default='#6862e8',
                            validators=[RegexValidator(r'^#[0-9a-fA-F]{6}$')])

    class Meta:
        ordering = ['name']
        constraints = [models.UniqueConstraint(fields=['owner', 'name'], name='category_per_owner')]

    def __str__(self):
        return self.name


class ImportBatch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    filename = models.CharField(max_length=180)
    rows = models.JSONField(default=list)
    errors = models.JSONField(default=list)
    status = models.CharField(max_length=12, default='preview', choices=[('preview', 'Проверена'), ('done', 'Импортирована')])
    imported_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class Transaction(models.Model):
    KINDS = [('expense', 'Расход'), ('income', 'Доход'), ('refund', 'Возврат покупки'),
             ('transfer_out', 'Перевод со счёта'), ('transfer_in', 'Перевод на счёт')]
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='entries')
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL)
    date = models.DateField('Дата')
    description = models.CharField('Описание', max_length=250)
    amount = models.DecimalField('Сумма, ₽', max_digits=12, decimal_places=2,
                                validators=[MinValueValidator(Decimal('0.01'))])
    kind = models.CharField('Тип', choices=KINDS, max_length=20, default='expense')
    batch = models.ForeignKey(ImportBatch, null=True, blank=True, on_delete=models.CASCADE, related_name='entries')
    dedup_key = models.CharField(max_length=80, null=True, blank=True)
    transfer_group = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-id']
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name='positive_amount'),
                       models.UniqueConstraint(fields=['account', 'dedup_key'], name='account_import_key')]
        indexes = [models.Index(fields=['account', 'date'])]

    @property
    def outgoing(self):
        return self.kind in ['expense', 'transfer_out']
