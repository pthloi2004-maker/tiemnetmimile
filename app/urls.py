from django.urls import path
from . import views

app_name = 'app'

urlpatterns = [

    # ==================== TRANG CHỦ / TỔNG QUAN ====================
    path('', views.dashboard, name='dashboard'),
    path('', views.dashboard, name='home'),

    # ==================== MÁY TÍNH ====================
    path('machines/',                    views.machine_list,   name='machine_list'),
    path('machines/add/',                views.machine_add,    name='machine_add'),
    path('machines/<int:machine_id>/',   views.machine_detail, name='machine_detail'),
    path('machines/<int:machine_id>/edit/', views.machine_edit, name='machine_edit'),
    path('machines/<int:machine_id>/toggle-lock/', views.machine_toggle_lock, name='machine_toggle_lock'),
    path('api/machines/',                views.api_machines,   name='api_machines'),
    path('api/machines/<int:machine_id>/action/', views.api_machine_action, name='api_machine_action'),

    # ==================== PHIÊN CHƠI — CHECK IN / OUT ====================
    path('checkin/',                     views.checkin,        name='checkin'),
    path('checkin/<int:machine_id>/',    views.checkin,        name='checkin_machine'),
    path('checkout/<int:session_id>/',   views.checkout,       name='checkout'),
    path('sessions/',                    views.session_list,   name='session_list'),
    path('sessions/<int:session_id>/',   views.session_detail, name='session_detail'),

    # ==================== DỊCH VỤ ====================
    path('services/',                    views.service_list,   name='service_list'),
    path('order-service/<int:session_id>/', views.order_service, name='order_service'),

    # ==================== HÀNG CHỜ ====================
    path('queue/',                       views.queue_view,     name='queue'),
    path('queue/add/',                   views.queue_add,      name='queue_add'),
    path('queue/serve/<int:queue_id>/',  views.queue_serve,    name='queue_serve'),

    # ==================== KHÁCH HÀNG ====================
    path('customers/',                   views.customer_list,   name='customer_list'),
    path('customers/add/',               views.customer_add,    name='customer_add'),
    path('customers/<int:customer_id>/', views.customer_detail, name='customer_detail'),

    # ==================== MÔ PHỎNG HỆ ĐIỀU HÀNH ====================
    path('simulation/',                  views.simulation,        name='simulation'),
    path('simulation/topics/',           views.os_topics,         name='os_topics'),
    path('simulation/import/',           views.import_simulation_data, name='import_simulation_data'),
    path('simulation/api/import/',       views.api_import_simulation_data, name='api_import_simulation_data'),
    path('simulation/banker/',           views.banker_simulation, name='banker_simulation'),
    path('simulation/dbdaa/',            views.dbdaa_simulation,  name='dbdaa_simulation'),
    path('simulation/banker-dbdaa-compare/', views.banker_dbdaa_compare, name='banker_dbdaa_compare'),
    path('simulation/scheduling/',       views.scheduling_simulation, name='scheduling_simulation'),
    path('simulation/omdrrs/',           views.omdrrs_simulation,     name='omdrrs_simulation'),
    path('simulation/scheduling/compare/', views.scheduling_compare, name='scheduling_compare'),
    path('simulation/memory/',           views.memory_simulation, name='memory_simulation'),
    path('simulation/synchronization/',   views.synchronization_simulation, name='synchronization_simulation'),

    # ==================== BÁO CÁO ====================
    path('report/',                      views.report,  name='report'),

    # ==================== XÁC THỰC ====================
    path('login/',                       views.login_view,    name='login'),
    path('logout/',                      views.logout_view,   name='logout'),
    path('register/',                    views.register_view, name='register'),
    path('auth/phone/',                  views.phone_login_request, name='phone_login'),
    path('auth/verify/',                 views.phone_login_verify,  name='phone_verify'),
    path('auth/qr-create/',             views.qr_token_create,     name='qr_create'),
    path('auth/qr-login/<str:token>/',  views.qr_login,            name='qr_login'),

    # ==================== E-COMMERCE STUBS ====================
    path('products/',                    views.product_list,  name='product_list'),
    path('products/<int:product_id>/<slug:slug>/', views.product_detail, name='product_detail'),
    path('cart/add/<int:product_id>/',  views.add_to_cart,   name='add_to_cart'),
    path('cart/',                        views.view_cart,     name='view_cart'),
    path('cart/remove/<int:item_id>/',  views.remove_item,   name='remove_item'),
    path('about/',                       views.about,         name='about'),
    path('contact/',                     views.contact,       name='contact'),
    path('search/',                      views.search,        name='search'),
]
