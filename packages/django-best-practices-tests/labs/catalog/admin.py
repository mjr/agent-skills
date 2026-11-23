from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    date_hierarchy = 'paid_at'
    list_display = ('id', 'status', 'paid_at')
