from django.contrib import admin

from .models import Order, Payment, Product


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    date_hierarchy = 'paid_at'
    list_display = ('id', 'status', 'paid_at')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    # The admin-* tests override these attributes one at a time.
    list_display = ('name', 'category')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'status')
