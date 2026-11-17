import io
from decimal import Decimal
from pathlib import Path
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from openpyxl import Workbook
from .models import Account, Category, Transaction, ImportBatch
from .importers import parse_statement, ImportProblem
from .services import money_summary, seed_demo


class FinanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username='alice', email='alice@example.com', password='Example-Password-21')
        cls.other = get_user_model().objects.create_user(username='bob', email='bob@example.com', password='Example-Password-22')
        cls.account = Account.objects.create(owner=cls.user, name='Карта', bank='Демо', opening_balance=1000)
        cls.other_account = Account.objects.create(owner=cls.other, name='Чужая карта', bank='Демо')

    def setUp(self):
        self.client.force_login(self.user)

    def csv_file(self, body=None):
        content = body or 'date;description;amount;currency;type\n2026-11-01;Продукты;-100.50;RUB;expense\n2026-11-02;Зарплата;500;RUB;income\n'
        return SimpleUploadedFile('sample.csv', content.encode('utf-8-sig'))

    def upload(self, file=None):
        result = self.client.post(reverse('import_upload'), {'account': self.account.pk, 'file': file or self.csv_file()})
        self.assertEqual(result.status_code, 302)
        return ImportBatch.objects.latest('created_at')

    def test_guest_is_redirected(self):
        self.client.logout()
        self.assertRedirects(self.client.get('/'), '/login/?next=/', fetch_redirect_response=False)

    def test_all_user_pages_render(self):
        for route in ['dashboard', 'operations', 'analytics', 'accounts', 'categories', 'account_create', 'operation_create', 'transfer', 'import_upload']:
            with self.subTest(route=route):
                self.assertEqual(self.client.get(reverse(route)).status_code, 200)

    def test_signup_and_email_login(self):
        self.client.logout()
        response = self.client.post(reverse('signup'), {'first_name': 'Елена', 'username': 'elena', 'email': 'ELENA@example.com',
            'password1': 'Secret-For-Testing-2026', 'password2': 'Secret-For-Testing-2026'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Category.objects.filter(owner__username='elena').exists())
        self.client.logout()
        response = self.client.post(reverse('login'), {'username': 'elena@example.com', 'password': 'Secret-For-Testing-2026'})
        self.assertEqual(response.status_code, 302)

    def test_login_rate_limit(self):
        self.client.logout()
        for _ in range(8):
            self.client.post(reverse('login'), {'username': 'alice', 'password': 'wrong'})
        self.assertEqual(self.client.post(reverse('login'), {'username': 'alice', 'password': 'wrong'}).status_code, 429)

    def test_owner_scoping(self):
        for route in ['account_edit', 'account_delete']:
            self.assertEqual(self.client.get(reverse(route, args=[self.other_account.pk])).status_code, 404)
            self.assertEqual(self.client.post(reverse(route, args=[self.other_account.pk])).status_code, 404)
        response = self.client.get(reverse('operations'), {'account': self.other_account.pk})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['page_obj'].object_list.exists())

    def test_foreign_category_and_account_rejected(self):
        category = Category.objects.create(owner=self.other, name='Чужое')
        data = {'description': 'Нельзя', 'amount': '20', 'kind': 'expense', 'date': '2026-11-01',
                'account': self.other_account.pk, 'category': category.pk}
        response = self.client.post(reverse('operation_create'), data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Transaction.objects.count(), 0)

    def test_manual_transaction_and_balance(self):
        data = {'description': 'Кофе', 'amount': '125.50', 'kind': 'expense', 'date': '2026-11-01', 'account': self.account.pk}
        self.assertEqual(self.client.post(reverse('operation_create'), data).status_code, 302)
        self.assertEqual(self.account.balance, Decimal('874.50'))
        data['amount'] = '-10'
        self.assertEqual(self.client.post(reverse('operation_create'), data).status_code, 200)
        self.assertEqual(Transaction.objects.count(), 1)

    def test_transfer_and_refund(self):
        dest = Account.objects.create(owner=self.user, name='Вторая', bank='Демо')
        response = self.client.post(reverse('transfer'), {'source': self.account.pk, 'destination': dest.pk, 'amount': '200', 'date': '2026-11-01'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(dest.balance, Decimal('200'))
        self.assertEqual(self.account.balance, Decimal('800'))
        summary = money_summary(Transaction.objects.all())
        self.assertEqual(summary['income'], 0)
        self.assertEqual(summary['net_expense'], 0)
        Transaction.objects.create(account=self.account, description='Покупка', date='2026-11-01', kind='expense', amount=100)
        Transaction.objects.create(account=self.account, description='Возврат', date='2026-11-02', kind='refund', amount=25)
        self.assertEqual(money_summary(Transaction.objects.all())['net_expense'], Decimal('75'))
        pair = Transaction.objects.filter(transfer_group__isnull=False).first()
        self.client.post(reverse('operation_delete', args=[pair.pk]))
        self.assertEqual(Transaction.objects.filter(transfer_group__isnull=False).count(), 0)

    def test_csv_preview_confirmation_and_duplicates(self):
        batch = self.upload()
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(self.client.get(reverse('import_preview', args=[batch.pk])).status_code, 200)
        self.client.post(reverse('import_preview', args=[batch.pk]), {'rows': ['0', '1']})
        self.assertEqual(Transaction.objects.count(), 2)
        self.client.post(reverse('import_preview', args=[batch.pk]), {'rows': ['0', '1']})
        self.assertEqual(Transaction.objects.count(), 2)
        duplicate = self.upload()
        self.client.post(reverse('import_preview', args=[duplicate.pk]), {'rows': ['0', '1']})
        self.assertEqual(Transaction.objects.count(), 2)

    def test_identical_purchases_in_one_file_preserved(self):
        content = 'date;description;amount\n2026-11-01;Кофе;-100\n2026-11-01;Кофе;-100\n'
        batch = self.upload(self.csv_file(content))
        self.client.post(reverse('import_preview', args=[batch.pk]), {'rows': ['0', '1']})
        self.assertEqual(Transaction.objects.count(), 2)

    def test_invalid_row_skipped_and_non_rub_rejected(self):
        file = self.csv_file('date;description;amount;currency\n2026-11-01;Кофе;-100;RUB\n2026-11-01;Отель;-100;USD\nне дата;Покупка;-100;RUB\n')
        rows, errors = parse_statement(file)
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(errors), 2)

    def test_xlsx_parser(self):
        wb, buffer = Workbook(), io.BytesIO()
        wb.active.append(['Дата операции', 'Описание', 'Сумма', 'Валюта'])
        wb.active.append(['01.11.2026', 'Аптека', -500.25, 'RUB'])
        wb.save(buffer)
        rows, errors = parse_statement(SimpleUploadedFile('sample.xlsx', buffer.getvalue()))
        self.assertEqual(rows[0]['amount'], '500.25')
        self.assertEqual(rows[0]['kind'], 'expense')
        self.assertEqual(errors, [])

    def test_sample_pdf_parser(self):
        data = (settings.BASE_DIR / 'samples' / 'statement.pdf').read_bytes()
        rows, errors = parse_statement(SimpleUploadedFile('sample.pdf', data))
        self.assertEqual(len(rows), 4)
        self.assertEqual(errors, [])

    def test_unsupported_structure_rejected(self):
        with self.assertRaises(ImportProblem):
            parse_statement(self.csv_file('unknown;columns\n1;2'))

    def test_preview_is_private(self):
        batch = self.upload()
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('import_preview', args=[batch.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('import_preview', args=[batch.pk]), {'rows': ['0']}).status_code, 404)

    def test_csrf_protection(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(reverse('account_delete', args=[self.account.pk])).status_code, 403)
        self.assertTrue(Account.objects.filter(pk=self.account.pk).exists())

    def test_delete_batch_removes_only_its_operations(self):
        batch = self.upload()
        self.client.post(reverse('import_preview', args=[batch.pk]), {'rows': ['0']})
        manual = Transaction.objects.create(account=self.account, date='2026-11-01', description='Наличные', amount=100, kind='expense')
        self.client.post(reverse('batch_delete', args=[batch.pk]))
        self.assertEqual(list(Transaction.objects.values_list('pk', flat=True)), [manual.pk])

    def test_demo_idempotent(self):
        fresh = get_user_model().objects.create_user(username='empty', email='empty@example.com')
        self.assertTrue(seed_demo(fresh))
        count = Transaction.objects.count()
        self.assertFalse(seed_demo(fresh))
        self.assertEqual(Transaction.objects.count(), count)

    def test_invalid_filters_do_not_crash(self):
        self.assertEqual(self.client.get(reverse('operations'), {'start': 'hello', 'min_amount': 'x'}).status_code, 200)

    def test_password_reset_generates_link(self):
        from django.core import mail
        self.client.logout()
        self.client.post(reverse('password_reset'), {'email': 'alice@example.com'})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('/password/', mail.outbox[0].body)
