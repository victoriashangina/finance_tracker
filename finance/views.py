import csv
import hashlib
import io
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.paginator import Paginator
from django.db import transaction as db_transaction
from django.db.models import Sum, F
from django.db.models.functions import TruncMonth
from django.http import HttpResponse, FileResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST
from openpyxl import Workbook

from .forms import RegisterForm, LoginForm, AccountForm, CategoryForm, TransactionForm, TransferForm, UploadForm, FilterForm
from .models import Account, Category, Transaction, ImportBatch, LoginAttempt
from .importers import parse_statement, ImportProblem
from .services import ensure_categories, guess_category, money_summary, category_summary, seed_demo


def health(request):
    return HttpResponse('ok', content_type='text/plain')


class SecureLoginView(LoginView):
    template_name = 'registration/login.html'
    authentication_form = LoginForm

    def post(self, request, *args, **kwargs):
        self.attempt_key = hashlib.sha256(request.POST.get('username', '').strip().lower().encode()).hexdigest()
        cutoff = timezone.now() - timedelta(minutes=15)
        LoginAttempt.objects.filter(window_start__lt=cutoff).delete()
        if LoginAttempt.objects.filter(key=self.attempt_key, failures__gte=8).exists():
            form = self.get_form()
            form.is_valid()
            form.add_error(None, 'Слишком много попыток входа. Попробуй через 15 минут.')
            return self.render_to_response(self.get_context_data(form=form), status=429)
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        obj, _ = LoginAttempt.objects.get_or_create(key=self.attempt_key, defaults={'window_start': timezone.now()})
        LoginAttempt.objects.filter(pk=obj.pk).update(failures=F('failures') + 1)
        return super().form_invalid(form)

    def form_valid(self, form):
        LoginAttempt.objects.filter(key=self.attempt_key).delete()
        return super().form_valid(form)


def signup(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with db_transaction.atomic():
            user = form.save()
            ensure_categories(user)
        login(request, user, backend='finance.auth.EmailOrUsernameBackend')
        messages.success(request, 'Добро пожаловать! Добавь счёт или загрузи демонстрационные данные.')
        return redirect('dashboard')
    return render(request, 'registration/signup.html', {'form': form})


def filtered(request, month_default=False):
    data = request.GET.copy()
    if month_default and not request.GET:
        today = timezone.localdate()
        data.update({'start': today.replace(day=1).isoformat(), 'end': today.isoformat()})
    form = FilterForm(data, user=request.user)
    qs = Transaction.objects.filter(account__owner=request.user).select_related('account', 'category')
    if not form.is_valid():
        return qs.none(), form
    cd = form.cleaned_data
    for field, lookup in [('start', 'date__gte'), ('end', 'date__lte'), ('account', 'account'),
                          ('category', 'category'), ('kind', 'kind'), ('q', 'description__icontains'),
                          ('min_amount', 'amount__gte'), ('max_amount', 'amount__lte')]:
        if cd.get(field) is not None and cd.get(field) != '':
            qs = qs.filter(**{lookup: cd[field]})
    return qs, form


@login_required
def dashboard(request):
    qs, form = filtered(request, month_default=True)
    accounts = list(Account.objects.filter(owner=request.user))
    cats, gradient = category_summary(qs)
    return render(request, 'finance/dashboard.html', {
        'title': 'Обзор', 'accounts': accounts, 'has_accounts': bool(accounts),
        'balance': sum((a.balance for a in accounts), Decimal('0')), 'summary': money_summary(qs),
        'transactions': qs[:7], 'categories': cats[:5], 'gradient': gradient, 'filter_form': form})


@login_required
def operations(request):
    qs, form = filtered(request)
    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'finance/operations.html', {'title': 'Операции', 'filter_form': form,
        'page_obj': Paginator(qs, 20).get_page(request.GET.get('page')), 'params': params.urlencode(), 'summary': money_summary(qs)})


@login_required
def analytics(request):
    qs, form = filtered(request, month_default=True)
    cats, gradient = category_summary(qs)
    banks = qs.filter(kind='expense').values('account__name', 'account__bank').annotate(total=Sum('amount')).order_by('-total')
    monthly = list(qs.filter(kind='expense').annotate(month=TruncMonth('date')).values('month').annotate(total=Sum('amount')).order_by('month'))
    peak = max((x['total'] for x in monthly), default=Decimal('1'))
    for item in monthly:
        item['height'] = max(3, float(item['total'] / peak * 100))
    return render(request, 'finance/analytics.html', {'title': 'Аналитика', 'filter_form': form,
        'summary': money_summary(qs), 'categories': cats, 'gradient': gradient, 'banks': banks, 'monthly': monthly})


@login_required
def accounts(request):
    return render(request, 'finance/accounts.html', {'title': 'Мои счета', 'accounts': Account.objects.filter(owner=request.user)})


@login_required
def account_form(request, pk=None):
    obj = get_object_or_404(Account, pk=pk, owner=request.user) if pk else None
    form = AccountForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        item = form.save(commit=False)
        item.owner = request.user
        item.save()
        messages.success(request, 'Счёт сохранён.')
        return redirect('accounts')
    return render(request, 'finance/form.html', {'title': 'Редактировать счёт' if obj else 'Новый счёт', 'form': form,
        'back': 'accounts', 'hint': 'Укажи баланс до первой добавляемой операции. Полный номер карты не нужен.'})


@login_required
def operation_form(request, pk=None):
    obj = get_object_or_404(Transaction, pk=pk, account__owner=request.user) if pk else None
    if obj and obj.transfer_group:
        messages.info(request, 'Связанный перевод можно удалить и создать заново через кнопку «Перевод».')
        return redirect('operations')
    form = TransactionForm(request.POST or None, instance=obj, user=request.user)
    if request.method == 'POST' and form.is_valid():
        item = form.save(commit=False)
        if not item.category:
            item.category = guess_category(item.description, request.user)
        item.save()
        messages.success(request, 'Операция сохранена.')
        return redirect('operations')
    return render(request, 'finance/form.html', {'title': 'Изменить операцию' if obj else 'Новая операция', 'form': form,
        'back': 'operations', 'hint': 'Сумму вводи положительным числом. Тип операции определяет, как изменится баланс.'})


@login_required
def transfer(request):
    form = TransferForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        cd, group = form.cleaned_data, uuid.uuid4()
        with db_transaction.atomic():
            Transaction.objects.create(account=cd['source'], date=cd['date'], amount=cd['amount'], kind='transfer_out',
                description=f"Перевод → {cd['destination'].name}", transfer_group=group)
            Transaction.objects.create(account=cd['destination'], date=cd['date'], amount=cd['amount'], kind='transfer_in',
                description=f"Перевод ← {cd['source'].name}", transfer_group=group)
        messages.success(request, 'Перевод записан на обоих счетах. Расходы и доходы не изменились.')
        return redirect('operations')
    return render(request, 'finance/form.html', {'title': 'Между своими счетами', 'form': form, 'back': 'operations',
        'hint': 'Это запись движения денег для учёта. Приложение не переводит деньги в банке.'})


@login_required
def categories(request):
    form = CategoryForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        if Category.objects.filter(owner=request.user, name=form.cleaned_data['name']).exists():
            form.add_error('name', 'Такая категория уже есть.')
        else:
            item = form.save(commit=False)
            item.owner = request.user
            item.save()
            messages.success(request, 'Категория добавлена.')
            return redirect('categories')
    return render(request, 'finance/categories.html', {'title': 'Категории', 'form': form, 'categories': Category.objects.filter(owner=request.user)})


@login_required
def delete_item(request, model, pk):
    mapping = {'account': (Account, {'owner': request.user}, 'accounts'),
               'operation': (Transaction, {'account__owner': request.user}, 'operations'),
               'category': (Category, {'owner': request.user}, 'categories'),
               'batch': (ImportBatch, {'owner': request.user}, 'import_upload')}
    Model, scope, back = mapping[model]
    obj = get_object_or_404(Model, pk=pk, **scope)
    if request.method == 'POST':
        with db_transaction.atomic():
            if model == 'operation' and obj.transfer_group:
                Transaction.objects.filter(account__owner=request.user, transfer_group=obj.transfer_group).delete()
            else:
                if model == 'account':
                    groups = list(obj.entries.exclude(transfer_group=None).values_list('transfer_group', flat=True))
                    Transaction.objects.filter(account__owner=request.user, transfer_group__in=groups).delete()
                obj.delete()
        messages.success(request, 'Данные удалены.')
        return redirect(back)
    texts = {'account': 'Будут удалены все операции этого счёта, импорты и обе стороны связанных переводов.',
             'operation': 'Операция исчезнет из истории и аналитики. Для связанного перевода удалятся обе записи.',
             'category': 'Операции сохранятся с отметкой «Без категории».',
             'batch': 'Будут удалены операции, добавленные этим импортом. Другие операции сохранятся.'}
    return render(request, 'finance/delete.html', {'title': 'Удаление данных', 'warning': texts[model], 'object': obj, 'back': back})


@login_required
def import_upload(request):
    form = UploadForm(request.POST or None, request.FILES or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        try:
            rows, errors = parse_statement(form.cleaned_data['file'])
        except ImportProblem as exc:
            form.add_error('file', str(exc))
        else:
            batch = ImportBatch.objects.create(owner=request.user, account=form.cleaned_data['account'],
                filename=Path(form.cleaned_data['file'].name).name[:180], rows=rows, errors=errors)
            return redirect('import_preview', pk=batch.pk)
    return render(request, 'finance/import.html', {'title': 'Импорт выписки', 'form': form,
        'batches': ImportBatch.objects.filter(owner=request.user).select_related('account')[:10]})


@login_required
def import_preview(request, pk):
    batch = get_object_or_404(ImportBatch, pk=pk, owner=request.user)
    if request.method == 'POST':
        selected = set(request.POST.getlist('rows'))
        with db_transaction.atomic():
            batch = ImportBatch.objects.select_for_update().get(pk=batch.pk)
            if batch.status == 'done':
                messages.info(request, 'Эта выписка уже импортирована.')
                return redirect('operations')
            # Lock the account as well: concurrent imports for the same account serialize.
            Account.objects.select_for_update().get(pk=batch.account_id)
            existing = set(batch.account.entries.exclude(dedup_key=None).values_list('dedup_key', flat=True))
            cats, count = ensure_categories(request.user), 0
            for i, row in enumerate(batch.rows):
                if str(i) not in selected:
                    continue
                key = row['dedup_key']
                if key in existing:
                    if not request.POST.get('keep_duplicates'):
                        continue
                    # User explicitly opted in to retaining probable duplicates.
                    key = str(uuid.uuid4())
                Transaction.objects.create(account=batch.account, batch=batch, date=row['date'], amount=row['amount'],
                    description=row['description'], kind=row['kind'], dedup_key=key,
                    category=guess_category(row['description'], request.user, cats))
                existing.add(key)
                count += 1
            batch.status, batch.imported_count = 'done', count
            batch.save(update_fields=['status', 'imported_count'])
        messages.success(request, f'Импорт завершён: добавлено операций — {count}.')
        return redirect('operations')
    existing = set(batch.account.entries.exclude(dedup_key=None).values_list('dedup_key', flat=True))
    rows = [dict(row, index=i, duplicate=row['dedup_key'] in existing, kind_label=dict(Transaction.KINDS)[row['kind']])
            for i, row in enumerate(batch.rows)]
    return render(request, 'finance/preview.html', {'title': 'Проверка выписки', 'batch': batch,
        'rows': rows, 'duplicates': sum(r['duplicate'] for r in rows), 'fresh': sum(not r['duplicate'] for r in rows)})


@login_required
@require_POST
def demo(request):
    with db_transaction.atomic():
        from django.contrib.auth import get_user_model
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        created = seed_demo(request.user)
    messages.success(request, 'Демонстрационные данные добавлены.' if created else 'Демо доступно только в пустом кабинете.')
    return redirect('dashboard')


@login_required
def sample(request, extension):
    if extension not in {'csv', 'xlsx', 'pdf'}:
        raise Http404
    rows = [['date', 'description', 'amount', 'currency', 'type'],
            ['2026-11-01', 'Продукты', '-1250.50', 'RUB', 'expense'],
            ['2026-11-02', 'Зарплата', '85000.00', 'RUB', 'income'],
            ['2026-11-03', 'Кофейня', '-390.00', 'RUB', 'expense'],
            ['2026-11-04', 'Возврат заказа', '450.00', 'RUB', 'refund']]
    if extension == 'xlsx':
        wb, output = Workbook(), io.BytesIO()
        for row in rows:
            wb.active.append(row)
        wb.save(output)
        response = HttpResponse(output.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    elif extension == 'pdf':
        return FileResponse(open(settings.BASE_DIR / 'samples' / 'statement.pdf', 'rb'), as_attachment=True, filename='statement.pdf')
    else:
        output = io.StringIO()
        csv.writer(output, delimiter=';').writerows(rows)
        response = HttpResponse('\ufeff' + output.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="statement.{extension}"'
    return response
