from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Account, Category, Transaction, ImportBatch

admin.site.register(User, UserAdmin)
admin.site.register([Account, Category, Transaction, ImportBatch])
admin.site.site_header = 'Поток · управление'
admin.site.site_title = 'Поток'
