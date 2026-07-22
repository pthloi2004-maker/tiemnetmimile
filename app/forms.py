from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Session, Customer, Queue, Service, Machine


# ==================== ĐĂNG KÝ TÀI KHOẢN NHÂN VIÊN ====================
class StaffRegisterForm(UserCreationForm):
    class Meta:
        model  = User
        fields = ['username', 'email']
        labels = {
            'username': 'Tên đăng nhập',
            'email':    'Email',
        }


# ==================== NHẬN KHÁCH / CHECK-IN ====================
class CheckinForm(forms.ModelForm):
    """Form nhận khách vào máy"""

    class Meta:
        model  = Session
        fields = [
            'customer_name', 'customer', 'machine',
            'game_name', 'planned_minutes',
            'used_headset', 'used_account', 'used_ram_gb',
        ]
        labels = {
            'customer_name':    'Tên Khách (nhanh)',
            'customer':         'Thành Viên (nếu có)',
            'machine':          'Máy',
            'game_name':        'Game / Hoạt Động',
            'planned_minutes':  'Thời Gian Dự Kiến (phút)',
            'used_headset':     'Mượn Tai Nghe',
            'used_account':     'Dùng Tài Khoản Game',
            'used_ram_gb':      'RAM Cần (GB)',
        }
        widgets = {
            'machine':       forms.Select(attrs={'class': 'form-control'}),
            'customer':      forms.Select(attrs={'class': 'form-control'}),
            'planned_minutes': forms.NumberInput(attrs={'min': 30, 'step': 30}),
            'used_ram_gb':   forms.NumberInput(attrs={'min': 0, 'max': 64}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Chỉ hiện máy trống
        from .models import Machine
        self.fields['machine'].queryset = Machine.objects.filter(status='trong')
        self.fields['machine'].empty_label = 'Chọn máy trống...'
        self.fields['customer'].queryset = Customer.objects.all()
        self.fields['customer'].empty_label = 'Chọn thành viên (nếu có)'
        self.fields['customer'].required = False
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                continue
            css = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = (css + ' form-control').strip()


# ==================== QUẢN LÝ MÁY TÍNH ====================
class MachineForm(forms.ModelForm):
    class Meta:
        model = Machine
        fields = [
            'name', 'machine_type', 'status', 'hourly_rate',
            'has_headset', 'has_account', 'ram_gb', 'note', 'image',
        ]
        labels = {
            'name': 'Tên Máy',
            'machine_type': 'Loại Máy',
            'status': 'Trạng Thái',
            'hourly_rate': 'Giá/Giờ (₫)',
            'has_headset': 'Có Tai Nghe',
            'has_account': 'Có Tài Khoản Game',
            'ram_gb': 'RAM (GB)',
            'note': 'Ghi Chú',
            'image': 'Ảnh Máy',
        }
        widgets = {
            'hourly_rate': forms.NumberInput(attrs={'min': 0}),
            'ram_gb': forms.NumberInput(attrs={'min': 0}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                continue
            css = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = (css + ' form-control').strip()


# ==================== THÊM KHÁCH HÀNG THÀNH VIÊN ====================
class CustomerForm(forms.ModelForm):
    class Meta:
        model  = Customer
        fields = ['name', 'phone', 'member_type', 'balance']
        labels = {
            'name':        'Họ Tên',
            'phone':       'Số Điện Thoại',
            'member_type': 'Loại Thành Viên',
            'balance':     'Số Dư Nạp (₫)',
        }


# ==================== FORM HÀNG CHỜ ====================
class QueueForm(forms.ModelForm):
    class Meta:
        model  = Queue
        fields = ['customer_name', 'phone', 'preferred_type', 'preferred_machine', 'planned_minutes', 'note']
        labels = {
            'customer_name':    'Tên Khách',
            'phone':            'Số Điện Thoại',
            'preferred_type':   'Loại Máy Muốn',
            'preferred_machine':'Máy Cụ Thể (nếu muốn)',
            'planned_minutes':  'Dự Kiến Chơi (phút)',
            'note':             'Ghi Chú',
        }
        widgets = {
            'note': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['preferred_machine'].queryset = Machine.objects.filter(
            status__in=['trong', 'dang_dung']
        )
        self.fields['preferred_machine'].empty_label = 'Không yêu cầu máy cụ thể'
        self.fields['preferred_machine'].required = False
        for name, field in self.fields.items():
            css = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = (css + ' form-control').strip()


# ==================== FORM ĐẶT DỊCH VỤ ====================
class ServiceOrderForm(forms.Form):
    service  = forms.ModelChoiceField(
        queryset=Service.objects.filter(available=True),
        label='Dịch Vụ'
    )
    quantity = forms.IntegerField(min_value=1, initial=1, label='Số Lượng')


# ==================== FORM LẬP LỊCH (MÔ PHỎNG) ====================
class SchedulingForm(forms.Form):
    ALGO_CHOICES = [
        ('fcfs', 'FCFS — First Come First Serve'),
        ('sjf',  'SJF — Shortest Job First'),
        ('rr',   'Round Robin'),
    ]
    algorithm = forms.ChoiceField(
        choices=ALGO_CHOICES,
        label='Giải Thuật',
        initial='fcfs',
    )
    quantum = forms.IntegerField(
        min_value=1, initial=30,
        label='Time Quantum (phút) — chỉ dùng cho Round Robin',
        required=False,
    )
    include_queue = forms.BooleanField(
        required=False, initial=True,
        label='Bao gồm cả khách đang chờ (Queue)',
    )
    include_active = forms.BooleanField(
        required=False, initial=True,
        label='Bao gồm cả phiên đang chạy (Active Sessions)',
    )


class PhoneRequestForm(forms.Form):
    phone = forms.CharField(max_length=20, label='Số điện thoại')


class OTPVerifyForm(forms.Form):
    phone = forms.CharField(max_length=20, label='Số điện thoại')
    code = forms.CharField(max_length=8, label='Mã OTP')