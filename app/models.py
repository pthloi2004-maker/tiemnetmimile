from datetime import timedelta

from django.db import models
from django.contrib.auth.models import User
from django.db.models import Index
from django.utils import timezone


# ==================== MÁY TÍNH ====================
class Machine(models.Model):
    TYPE_CHOICES = [
        ('thuong', 'Máy Thường'),
        ('gaming', 'Máy Gaming'),
        ('vip', 'Phòng VIP'),
    ]
    STATUS_CHOICES = [
        ('trong', 'Trống'),
        ('dang_dung', 'Đang Dùng'),
        ('bao_tri', 'Bảo Trì'),
        ('loi', 'Lỗi/Kết Nối'),
        ('khoa', 'Khóa'),
    ]

    name         = models.CharField(max_length=50, unique=True, verbose_name='Tên Máy')         # PC01, PC02...
    machine_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='thuong',
                                     verbose_name='Loại Máy')
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default='trong',
                                     verbose_name='Trạng Thái')
    hourly_rate  = models.DecimalField(max_digits=10, decimal_places=0, default=10000,
                                        verbose_name='Giá/Giờ (₫)')

    # Cấu hình tài nguyên (dùng cho Banker Algorithm)
    has_headset  = models.BooleanField(default=True,  verbose_name='Có Tai Nghe')
    has_account  = models.BooleanField(default=False, verbose_name='Có Tài Khoản Game')
    ram_gb       = models.PositiveIntegerField(default=8, verbose_name='RAM (GB)')

    note         = models.TextField(blank=True, verbose_name='Ghi Chú')
    image        = models.ImageField(blank=True, null=True,
                                     upload_to='machine_images/',
                                     verbose_name='Ảnh máy')

    class Meta:
        verbose_name = 'Máy Tính'
        verbose_name_plural = 'Mimi Lê — Máy Tính'
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.get_machine_type_display()})'

    def is_available(self):
        return self.status == 'trong'

    def is_locked(self):
        return self.status == 'khoa'

    def is_error(self):
        return self.status == 'loi'

    def toggle_lock(self):
        self.status = 'trong' if self.is_locked() else 'khoa'
        self.save()


# ==================== KHÁCH HÀNG ====================
class Customer(models.Model):
    MEMBER_CHOICES = [
        ('vangLai', 'Vãng Lai'),
        ('thanhVien', 'Thành Viên'),
        ('vip', 'VIP'),
    ]

    name        = models.CharField(max_length=100, verbose_name='Tên Khách')
    phone       = models.CharField(max_length=15, blank=True, verbose_name='Số Điện Thoại')
    member_type = models.CharField(max_length=20, choices=MEMBER_CHOICES, default='vangLai',
                                    verbose_name='Loại Thành Viên')
    balance     = models.DecimalField(max_digits=12, decimal_places=0, default=0,
                                       verbose_name='Số Dư (₫)')
    created     = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Khách Hàng'
        verbose_name_plural = 'Mimi Lê — Khách Hàng'
        ordering = ['-created']

    def __str__(self):
        return f'{self.name} ({self.get_member_type_display()})'


# ==================== PHIÊN CHƠI (SESSION) ====================
class Session(models.Model):
    STATUS_CHOICES = [
        ('dang_chay', 'Đang Chạy'),
        ('hoan_thanh', 'Hoàn Thành'),
        ('tam_dung', 'Tạm Dừng'),
    ]

    # Liên kết
    user        = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='Nhân Viên Tạo')
    customer    = models.ForeignKey(Customer, null=True, blank=True,
                                     on_delete=models.SET_NULL, verbose_name='Khách Hàng')
    customer_name = models.CharField(max_length=100, blank=True, verbose_name='Tên Khách (nhanh)')
    machine     = models.ForeignKey(Machine, on_delete=models.CASCADE, verbose_name='Máy')

    # Thời gian
    start_time  = models.DateTimeField(default=timezone.now, verbose_name='Giờ Bắt Đầu')
    end_time    = models.DateTimeField(null=True, blank=True, verbose_name='Giờ Kết Thúc')

    # Hoạt động / trò chơi
    game_name   = models.CharField(max_length=100, blank=True, verbose_name='Game / Hoạt Động')
    promo_code  = models.CharField(max_length=50, blank=True, verbose_name='Mã Khuyến Mãi')
    discount_percent = models.PositiveIntegerField(default=0, verbose_name='Giảm Giá (%)')

    # Tài nguyên đã cấp (dùng cho Banker)
    used_headset  = models.BooleanField(default=False, verbose_name='Dùng Tai Nghe')
    used_account  = models.BooleanField(default=False, verbose_name='Dùng Tài Khoản Game')
    used_ram_gb   = models.PositiveIntegerField(default=0, verbose_name='RAM Sử Dụng (GB)')

    # Kế hoạch (dùng cho lập lịch)
    planned_minutes = models.PositiveIntegerField(default=60, verbose_name='Thời Gian Dự Kiến (phút)')

    # Thanh toán
    total_cost  = models.DecimalField(max_digits=12, decimal_places=0, default=0,
                                       verbose_name='Tổng Tiền (₫)')
    paid        = models.BooleanField(default=False, verbose_name='Đã Thanh Toán')
    status      = models.CharField(max_length=20, choices=STATUS_CHOICES, default='dang_chay',
                                    verbose_name='Trạng Thái')

    class Meta:
        verbose_name = 'Phiên Chơi'
        verbose_name_plural = 'Mimi Lê — Phiên Chơi'
        ordering = ['-start_time']

    def __str__(self):
        name = self.customer.name if self.customer else self.customer_name
        return f'{self.machine.name} — {name} ({self.start_time.strftime("%H:%M %d/%m")})'

    def get_customer_name(self):
        if self.customer:
            return self.customer.name
        return self.customer_name or 'Khách vãng lai'

    def get_duration_minutes(self):
        """Số phút đã chơi tính đến hiện tại hoặc lúc kết thúc"""
        end = self.end_time or timezone.now()
        delta = end - self.start_time
        return max(1, int(delta.total_seconds() / 60))

    def get_end_time(self):
        return self.end_time or timezone.now()

    @property
    def expected_end_time(self):
        return self.start_time + timedelta(minutes=self.planned_minutes)

    def get_remaining_minutes(self):
        if self.status != 'dang_chay':
            return 0
        remaining = self.expected_end_time - timezone.now()
        return max(0, int(remaining.total_seconds() / 60))

    def get_time_rate(self, moment):
        """Giá mỗi giờ (VD: 8000₫/giờ)"""
        hour = moment.hour
        if 6 <= hour < 18:
            return 8000
        if hour >= 22 or hour < 6:
            return 6000
        return 7000

    def calculate_cost(self):
        """Tính tiền theo giá ngày/đêm và giảm giá nếu có."""
        end = self.get_end_time()
        current = self.start_time
        total = 0
        while current < end:
            # get_time_rate trả về giá/giờ, chia 60 để ra giá/phút
            total += self.get_time_rate(current) / 60
            current += timedelta(minutes=1)

        if self.discount_percent:
            total = total * (100 - self.discount_percent) / 100
        return round(total)

    def get_service_cost(self):
        """Tổng tiền dịch vụ đã gọi trong phiên."""
        return sum(item.get_cost() for item in self.services.all())

    def is_expired(self):
        return self.status == 'dang_chay' and timezone.now() >= self.expected_end_time

    def expire_if_overdue(self):
        if self.status != 'dang_chay':
            return False
        if timezone.now() < self.expected_end_time:
            return False

        self.end_time = self.expected_end_time
        self.status = 'hoan_thanh'
        self.total_cost = self.calculate_cost() + self.get_service_cost()
        self.paid = False
        self.save()

        machine = self.machine
        machine.status = 'khoa'
        machine.save()
        return True

    def get_arrival_minutes(self):
        """Phút kể từ 8h sáng — dùng cho Arrival Time trong lập lịch"""
        base = self.start_time.replace(hour=8, minute=0, second=0, microsecond=0)
        delta = self.start_time - base
        return max(0, int(delta.total_seconds() / 60))

    def get_resource_vector(self):
        """Trả về vector tài nguyên [headset, account, ram_gb] — dùng cho Banker"""
        return [
            1 if self.used_headset else 0,
            1 if self.used_account else 0,
            self.used_ram_gb,
        ]


# ==================== DỊCH VỤ (ĐỒ ĂN / ĐỒ UỐNG / PHỤ KIỆN) ====================
class Service(models.Model):
    CATEGORY_CHOICES = [
        ('do_uong', 'Đồ Uống'),
        ('do_an', 'Đồ Ăn'),
        ('phu_kien', 'Phụ Kiện'),
        ('khac', 'Khác'),
    ]

    name     = models.CharField(max_length=100, verbose_name='Tên Dịch Vụ')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='do_uong',
                                 verbose_name='Loại')
    price    = models.DecimalField(max_digits=10, decimal_places=0, verbose_name='Giá (₫)')
    stock    = models.IntegerField(default=100, verbose_name='Tồn Kho')
    available = models.BooleanField(default=True, verbose_name='Còn Bán')

    class Meta:
        verbose_name = 'Dịch Vụ'
        verbose_name_plural = 'Mimi Lê — Dịch Vụ'

    def __str__(self):
        return f'{self.name} — {self.price:,}₫'


# ==================== CHI TIẾT DỊCH VỤ TRONG PHIÊN ====================
class SessionService(models.Model):
    session  = models.ForeignKey(Session, related_name='services',
                                  on_delete=models.CASCADE, verbose_name='Phiên')
    service  = models.ForeignKey(Service, on_delete=models.CASCADE, verbose_name='Dịch Vụ')
    quantity = models.PositiveIntegerField(default=1, verbose_name='Số Lượng')
    price    = models.DecimalField(max_digits=10, decimal_places=0, verbose_name='Đơn Giá')

    class Meta:
        verbose_name = 'Dịch Vụ Trong Phiên'
        verbose_name_plural = 'Mimi Lê — Dịch Vụ Trong Phiên'

    def get_cost(self):
        return self.price * self.quantity


# ==================== HÀNG CHỜ ====================
class Queue(models.Model):
    customer_name   = models.CharField(max_length=100, verbose_name='Tên Khách')
    phone           = models.CharField(max_length=15, blank=True)
    preferred_type  = models.CharField(
        max_length=20,
        choices=Machine.TYPE_CHOICES,
        default='thuong',
        verbose_name='Loại Máy Muốn'
    )
    preferred_machine = models.ForeignKey(
        Machine, null=True, blank=True,
        on_delete=models.SET_NULL, verbose_name='Máy Cụ Thể (nếu muốn)'
    )
    arrived_at      = models.DateTimeField(default=timezone.now, verbose_name='Giờ Đến')
    planned_minutes = models.PositiveIntegerField(default=60, verbose_name='Dự Kiến Chơi (phút)')
    is_served       = models.BooleanField(default=False, verbose_name='Đã Được Phục Vụ')
    note            = models.TextField(blank=True, verbose_name='Ghi Chú')

    class Meta:
        verbose_name = 'Hàng Chờ'
        verbose_name_plural = 'Mimi Lê — Hàng Chờ'
        ordering = ['arrived_at']

    def __str__(self):
        return f'{self.customer_name} — chờ lúc {self.arrived_at.strftime("%H:%M")}'

    def get_arrival_minutes(self):
        base = self.arrived_at.replace(hour=8, minute=0, second=0, microsecond=0)
        return max(0, int((self.arrived_at - base).total_seconds() / 60))

    def get_estimated_wait_minutes(self):
        """
        Tính thời gian chờ dự kiến dựa trên các phiên đang chạy và
        những người đứng trước trong hàng chờ.
        """
        from django.utils import timezone
        now = timezone.now()

        # Lấy các phiên đang chạy có thời gian dự kiến còn lại
        active_sessions = Session.objects.filter(status='dang_chay')
        total_wait = 0

        # Cộng thời gian còn lại của các máy đang bận
        for sess in active_sessions:
            remaining = sess.get_remaining_minutes()
            if remaining > 0:
                total_wait += remaining

        # Cộng thời gian dự kiến của những người đứng trước trong hàng chờ
        ahead = Queue.objects.filter(
            is_served=False,
            arrived_at__lt=self.arrived_at
        ).exclude(id=self.id)
        for q in ahead:
            total_wait += q.planned_minutes

        # Tính số máy trống trung bình để chia đều
        total_machines = Machine.objects.filter(
            status__in=['trong', 'dang_dung']
        ).count()
        busy_machines = Machine.objects.filter(status='dang_dung').count()
        free_machines = max(1, total_machines - busy_machines)

        estimated = total_wait // free_machines if free_machines > 0 else total_wait
        return max(0, estimated)


class OTPCode(models.Model):
    phone = models.CharField(max_length=20, verbose_name='Số điện thoại')
    code = models.CharField(max_length=8)
    created = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)

    class Meta:
        indexes = [Index(fields=['phone', 'code'])]

    def is_valid(self):
        return not self.used and (timezone.now() - self.created).total_seconds() < 10 * 60


class LoginToken(models.Model):
    """Simple short-lived token for QR login / one-click auth (dev-mode)."""
    token = models.CharField(max_length=64, unique=True)
    phone = models.CharField(max_length=20, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)

    def is_valid(self):
        return not self.used and (timezone.now() - self.created).total_seconds() < 5 * 60
