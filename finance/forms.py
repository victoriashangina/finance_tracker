from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Account, Category, Transaction


class RegisterForm(UserCreationForm):
    first_name = forms.CharField(label='Как тебя зовут', max_length=50)
    email = forms.EmailField(label='Электронная почта')

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ['first_name', 'username', 'email']
        help_texts = {'username': 'До 150 символов: буквы, цифры, точки, +, -, _. Без @.'}

    def clean_username(self):
        value = super().clean_username()
        if '@' in value:
            raise forms.ValidationError('Для логина используй буквы, цифры и знак подчёркивания без @.')
        return value

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if get_user_model().objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Эта почта уже используется.')
        return email


class LoginForm(AuthenticationForm):
    username = forms.CharField(label='Логин или электронная почта')


class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ['name', 'bank', 'last_four', 'opening_balance', 'color']


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'color']
        widgets = {'color': forms.TextInput(attrs={'type': 'color'})}


class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ['description', 'amount', 'kind', 'date', 'account', 'category']
        labels = {'account': 'Счёт', 'category': 'Категория'}
        widgets = {'date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'})}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['account'].queryset = Account.objects.filter(owner=user)
        self.fields['category'].queryset = Category.objects.filter(owner=user)
        self.fields['date'].initial = timezone.localdate()


class TransferForm(forms.Form):
    source = forms.ModelChoiceField(queryset=Account.objects.none(), label='Со счёта')
    destination = forms.ModelChoiceField(queryset=Account.objects.none(), label='На счёт')
    amount = forms.DecimalField(label='Сумма, ₽', max_digits=12, decimal_places=2, min_value=0.01)
    date = forms.DateField(label='Дата', initial=timezone.localdate, widget=forms.DateInput(attrs={'type': 'date'}))

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['source'].queryset = self.fields['destination'].queryset = Account.objects.filter(owner=user)

    def clean(self):
        data = super().clean()
        if data.get('source') and data.get('source') == data.get('destination'):
            raise forms.ValidationError('Выбери два разных счёта.')
        return data


class UploadForm(forms.Form):
    account = forms.ModelChoiceField(queryset=Account.objects.none(), label='На какой счёт загрузить операции')
    file = forms.FileField(label='Выписка CSV, XLSX или PDF', widget=forms.ClearableFileInput(attrs={'accept': '.csv,.xlsx,.pdf'}))

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['account'].queryset = Account.objects.filter(owner=user)

    def clean_file(self):
        f = self.cleaned_data['file']
        if f.size > 5 * 1024 * 1024:
            raise forms.ValidationError('Максимальный размер файла — 5 МБ.')
        if f.name.lower().split('.')[-1] not in {'csv', 'xlsx', 'pdf'}:
            raise forms.ValidationError('Выбери CSV, XLSX или текстовый PDF.')
        return f


class FilterForm(forms.Form):
    start = forms.DateField(required=False, label='С', widget=forms.DateInput(attrs={'type': 'date'}))
    end = forms.DateField(required=False, label='По', widget=forms.DateInput(attrs={'type': 'date'}))
    account = forms.ModelChoiceField(required=False, queryset=Account.objects.none(), label='Счёт', empty_label='Все счета')
    category = forms.ModelChoiceField(required=False, queryset=Category.objects.none(), label='Категория', empty_label='Все категории')
    kind = forms.ChoiceField(required=False, choices=[('', 'Все типы')] + Transaction.KINDS, label='Тип')
    q = forms.CharField(required=False, max_length=250, label='Поиск', widget=forms.TextInput(attrs={'placeholder': 'Магазин, услуга…'}))
    min_amount = forms.DecimalField(required=False, min_value=0, max_digits=12, decimal_places=2, label='Сумма от')
    max_amount = forms.DecimalField(required=False, min_value=0, max_digits=12, decimal_places=2, label='Сумма до')

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['account'].queryset = Account.objects.filter(owner=user)
        self.fields['category'].queryset = Category.objects.filter(owner=user)

    def clean(self):
        data = super().clean()
        if data.get('start') and data.get('end') and data['start'] > data['end']:
            raise forms.ValidationError('Начало периода должно быть раньше окончания.')
        if data.get('min_amount') is not None and data.get('max_amount') is not None and data['min_amount'] > data['max_amount']:
            raise forms.ValidationError('Минимальная сумма должна быть меньше максимальной.')
        return data
