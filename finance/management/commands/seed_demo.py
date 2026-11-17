from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction
from finance.services import seed_demo


class Command(BaseCommand):
    help = 'Add synthetic sample data to an existing empty user account.'

    def add_arguments(self, parser):
        parser.add_argument('--username', required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            user = get_user_model().objects.select_for_update().get(username=options['username'])
        except get_user_model().DoesNotExist as exc:
            raise CommandError('Сначала зарегистрируй пользователя через сайт.') from exc
        if seed_demo(user):
            self.stdout.write(self.style.SUCCESS('Демонстрационные данные добавлены.'))
        else:
            self.stdout.write('У пользователя уже есть счета. Данные не изменены.')
