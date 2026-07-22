from django.contrib import admin
from django.utils import timezone
from .models import Machine, Customer, Session, SessionService, Service, Queue


# ==================== MÁY TÍNH ====================
@admin.register(Machine)
class MachineAdmin(admin.ModelAdmin):
    list_display  = ['name', 'machine_type', 'status', 'hourly_rate',
                     'has_headset', 'has_account', 'ram_gb', 'image']
    list_filter   = ['status', 'machine_type', 'has_headset', 'has_account']
    list_editable = ['status', 'hourly_rate']
    search_fields = ['name']

    fieldsets = (
        ('Thông Tin Máy', {
            'fields': ('name', 'machine_type', 'status', 'hourly_rate', 'note', 'image')
        }),
        ('Tài Nguyên (Banker Algorithm)', {
            'fields': ('has_headset', 'has_account', 'ram_gb'),
            'description': 'Cấu hình tài nguyên dùng cho Banker Algorithm'
        }),
    )


# ==================== KHÁCH HÀNG ====================
@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display  = ['name', 'phone', 'member_type', 'balance', 'created']
    list_filter   = ['member_type']
    list_editable = ['member_type', 'balance']
    search_fields = ['name', 'phone']


# ==================== DỊCH VỤ ====================
@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display  = ['name', 'category', 'price', 'stock', 'available']
    list_filter   = ['category', 'available']
    list_editable = ['price', 'stock', 'available']
    search_fields = ['name']


# ==================== PHIÊN CHƠI ====================
class SessionServiceInline(admin.TabularInline):
    model  = SessionService
    extra  = 1
    fields = ['service', 'quantity', 'price']


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display  = ['machine', 'display_customer', 'start_time', 'end_time',
                     'status', 'display_duration', 'total_cost', 'paid']
    list_filter   = ['status', 'paid', 'machine__machine_type', 'start_time']
    list_editable = ['paid', 'status']
    search_fields = ['customer__name', 'customer_name', 'machine__name']
    readonly_fields = ['start_time']
    inlines = [SessionServiceInline]

    fieldsets = (
        ('Thông Tin Phiên', {
            'fields': ('user', 'customer', 'customer_name', 'machine',
                       'start_time', 'end_time', 'planned_minutes', 'status')
        }),
        ('Tài Nguyên Đã Cấp (Banker)', {
            'fields': ('used_headset', 'used_account', 'used_ram_gb'),
        }),
        ('Thanh Toán', {
            'fields': ('total_cost', 'paid'),
        }),
    )

    def display_customer(self, obj):
        return obj.get_customer_name()
    display_customer.short_description = 'Khách Hàng'

    def display_duration(self, obj):
        mins = obj.get_duration_minutes()
        h, m = divmod(mins, 60)
        return f'{h}h{m:02d}m'
    display_duration.short_description = 'Thời Gian'

    actions = ['action_checkout']

    def action_checkout(self, request, queryset):
        count = 0
        for sess in queryset.filter(status='dang_chay'):
            sess.end_time   = timezone.now()
            sess.total_cost = sess.calculate_cost()
            sess.status     = 'hoan_thanh'
            sess.paid       = True
            sess.save()
            sess.machine.status = 'trong'
            sess.machine.save()
            count += 1
        self.message_user(request, f'Đã trả máy cho {count} phiên.')
    action_checkout.short_description = 'Trả Máy (Checkout)'


# ==================== HÀNG CHỜ ====================
@admin.register(Queue)
class QueueAdmin(admin.ModelAdmin):
    list_display  = ['customer_name', 'phone', 'preferred_type',
                     'arrived_at', 'planned_minutes', 'is_served']
    list_filter   = ['preferred_type', 'is_served']
    list_editable = ['is_served']
    search_fields = ['customer_name', 'phone']