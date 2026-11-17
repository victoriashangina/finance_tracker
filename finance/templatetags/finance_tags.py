from decimal import Decimal, InvalidOperation
from django import template
from django.utils.safestring import mark_safe
register = template.Library()

@register.filter
def rub(value):
    try:
        return f'{Decimal(value or 0):,.2f}'.replace(',', '\u00a0').replace('.', ',') + ' ₽'
    except (InvalidOperation, TypeError, ValueError):
        return '0,00 ₽'

@register.simple_tag
def icon(name):
    paths = {
        'grid': '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
        'card': '<rect x="2" y="5" width="20" height="14" rx="3"/><path d="M2 10h20M6 15h4"/>',
        'list': '<path d="M8 6h13M8 12h13M8 18h13M3 6h.1M3 12h.1M3 18h.1"/>',
        'chart': '<path d="M4 20V10M10 20V4M16 20v-7M22 20V7"/>',
        'upload': '<path d="M12 16V3m-5 5 5-5 5 5M4 15v5a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5"/>',
        'tag': '<path d="M3 3h8l10 10-8 8L3 11Z"/><circle cx="7" cy="7" r="1"/>',
        'plus': '<path d="M12 5v14M5 12h14"/>',
        'arrow': '<path d="M5 12h14m-5-5 5 5-5 5"/>',
        'down': '<path d="M12 4v16m-5-5 5 5 5-5"/>',
        'up': '<path d="M12 20V4m-5 5 5-5 5 5"/>',
        'transfer': '<path d="M3 7h17m-4-4 4 4-4 4M21 17H4m4-4-4 4 4 4"/>',
        'logout': '<path d="M10 3H4v18h6M9 12h12m-5-5 5 5-5 5"/>',
        'menu': '<path d="M3 6h18M3 12h18M3 18h18"/>',
        'edit': '<path d="m16 3 5 5-12 12-6 1 1-6ZM13 6l5 5"/>',
        'trash': '<path d="M3 6h18M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7M14 10v7"/>',
        'shield': '<path d="m12 2 8 4v6c0 5-8 10-8 10S4 17 4 12V6Zm-4 10 3 3 5-6"/>',
    }
    return mark_safe('<svg class="icon" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">' + paths.get(name, paths['card']) + '</svg>')
