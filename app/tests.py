from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from .models import Machine, Customer, Session
from .scheduling_algorithms import (
    fcfs, sjf, round_robin, calc_stats,
    build_banker_data, banker_safety,
)
from .omdrrs_scheduler import schedule_omdrrs
from .q_learning_scheduler import schedule_q_learning
from .scheduling_benchmark import run_all_schedulers


# ==============================================================
# TEST GIẢI THUẬT LẬP LỊCH
# ==============================================================

class FCFSTestCase(TestCase):
    def setUp(self):
        self.processes = [
            {'pid': 1, 'name': 'P1', 'arrival': 0, 'burst': 8},
            {'pid': 2, 'name': 'P2', 'arrival': 1, 'burst': 4},
            {'pid': 3, 'name': 'P3', 'arrival': 2, 'burst': 9},
            {'pid': 4, 'name': 'P4', 'arrival': 3, 'burst': 5},
        ]

    def test_order(self):
        """FCFS phải xử lý theo thứ tự arrival"""
        tl = fcfs(self.processes)
        pids = [t['pid'] for t in tl]
        self.assertEqual(pids, [1, 2, 3, 4])

    def test_no_overlap(self):
        """Các đoạn trong timeline không được chồng nhau"""
        tl = fcfs(self.processes)
        for i in range(len(tl) - 1):
            self.assertLessEqual(tl[i]['end'], tl[i+1]['start'])

    def test_wait_time(self):
        tl = fcfs(self.processes)
        # P1: wait = 0, P2: wait = 8-1=7
        self.assertEqual(tl[0]['wait'], 0)
        self.assertEqual(tl[1]['wait'], 7)

    def test_empty(self):
        self.assertEqual(fcfs([]), [])


class SJFTestCase(TestCase):
    def setUp(self):
        self.processes = [
            {'pid': 1, 'name': 'P1', 'arrival': 0, 'burst': 6},
            {'pid': 2, 'name': 'P2', 'arrival': 1, 'burst': 2},
            {'pid': 3, 'name': 'P3', 'arrival': 2, 'burst': 8},
            {'pid': 4, 'name': 'P4', 'arrival': 3, 'burst': 3},
        ]

    def test_shortest_first(self):
        """Sau P1 kết thúc (t=6), P2 (burst=2) phải được chọn trước P4 (burst=3)"""
        tl = sjf(self.processes)
        pids = [t['pid'] for t in tl]
        # P1 first (at t=0 only P1 available), then shortest among available
        self.assertEqual(pids[0], 1)
        self.assertIn(2, pids[1:3])  # P2 hoặc P4 nhỏ nhất sau P1

    def test_empty(self):
        self.assertEqual(sjf([]), [])


class RoundRobinTestCase(TestCase):
    def setUp(self):
        self.processes = [
            {'pid': 1, 'name': 'P1', 'arrival': 0, 'burst': 10},
            {'pid': 2, 'name': 'P2', 'arrival': 0, 'burst':  5},
            {'pid': 3, 'name': 'P3', 'arrival': 0, 'burst':  8},
        ]

    def test_all_complete(self):
        """Mọi tiến trình phải hoàn thành"""
        tl = round_robin(self.processes, quantum=3)
        pids_done = {seg['pid'] for seg in tl}
        self.assertEqual(pids_done, {1, 2, 3})

    def test_total_burst(self):
        """Tổng thời gian chạy = tổng burst"""
        tl = round_robin(self.processes, quantum=3)
        total = sum(seg['end'] - seg['start'] for seg in tl)
        expected = sum(p['burst'] for p in self.processes)
        self.assertEqual(total, expected)

    def test_empty(self):
        self.assertEqual(round_robin([], quantum=2), [])


class OMDRRSTestCase(TestCase):
    def test_schedule_completes(self):
        processes = [
            {'pid': 1, 'name': 'P1', 'arrival': 0, 'burst': 5, 'priority': 3},
            {'pid': 2, 'name': 'P2', 'arrival': 1, 'burst': 3, 'priority': 1},
        ]
        tl = schedule_omdrrs(processes)
        self.assertTrue(len(tl) >= 2)
        total = sum(seg['end'] - seg['start'] for seg in tl)
        self.assertEqual(total, 8)


class QLearningTestCase(TestCase):
    def test_schedule_returns_timeline(self):
        processes = [
            {'pid': 1, 'name': 'P1', 'arrival': 0, 'burst': 6},
            {'pid': 2, 'name': 'P2', 'arrival': 2, 'burst': 4},
        ]
        result = schedule_q_learning(processes, episodes=40, seed=42)
        self.assertGreater(len(result['timeline']), 0)
        self.assertGreater(result['q_table_size'], 0)


class CompareBenchmarkTestCase(TestCase):
    def test_run_all_five(self):
        processes = [
            {'pid': 1, 'name': 'P1', 'arrival': 0, 'burst': 8},
            {'pid': 2, 'name': 'P2', 'arrival': 1, 'burst': 4},
        ]
        rows = run_all_schedulers(processes, quantum=10, q_episodes=30, seed=1)
        self.assertEqual(len(rows), 5)
        keys = {r['key'] for r in rows}
        self.assertEqual(keys, {'fcfs', 'sjf', 'rr', 'omdrrs', 'qlearning'})


class CalcStatsTestCase(TestCase):
    def test_stats(self):
        processes = [
            {'pid': 1, 'arrival': 0, 'burst': 4},
            {'pid': 2, 'arrival': 0, 'burst': 6},
        ]
        tl = fcfs(processes)
        stats = calc_stats(tl, processes)
        self.assertIn('avg_wait', stats)
        self.assertIn('avg_tat', stats)
        self.assertIn('cpu_util', stats)
        self.assertGreaterEqual(stats['cpu_util'], 0)
        self.assertLessEqual(stats['cpu_util'], 100)


# ==============================================================
# TEST BANKER ALGORITHM
# ==============================================================

class BankerSafetyTestCase(TestCase):
    """
    Ví dụ kinh điển:
      n=5, m=3 (A, B, C)
      Available = [3, 3, 2]
    """

    def setUp(self):
        self.available  = [3, 3, 2]
        self.allocation = [
            [0, 1, 0],
            [2, 0, 0],
            [3, 0, 2],
            [2, 1, 1],
            [0, 0, 2],
        ]
        self.need = [
            [7, 4, 3],
            [1, 2, 2],
            [6, 0, 0],
            [0, 1, 1],
            [4, 3, 1],
        ]

    def test_safe_state(self):
        result = banker_safety(5, self.available, self.allocation, self.need)
        self.assertTrue(result['safe'])

    def test_safe_sequence_length(self):
        result = banker_safety(5, self.available, self.allocation, self.need)
        self.assertEqual(len(result['safe_sequence']), 5)

    def test_unsafe_state(self):
        """Xóa tài nguyên → hệ thống không an toàn"""
        result = banker_safety(5, [0, 0, 0], self.allocation, self.need)
        self.assertFalse(result['safe'])


# ==============================================================
# TEST MODEL
# ==============================================================

class MachineModelTestCase(TestCase):
    def test_is_available(self):
        m = Machine(name='PC01', status='trong')
        self.assertTrue(m.is_available())

    def test_not_available(self):
        m = Machine(name='PC02', status='dang_dung')
        self.assertFalse(m.is_available())


class SessionModelTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='nhanvien', password='pass')
        self.machine = Machine.objects.create(name='PC01', hourly_rate=10000)

    def test_get_customer_name_fallback(self):
        sess = Session(machine=self.machine, user=self.user, customer_name='Khách Test')
        self.assertEqual(sess.get_customer_name(), 'Khách Test')

    def test_get_resource_vector(self):
        sess = Session(
            machine=self.machine, user=self.user,
            used_headset=True, used_account=False, used_ram_gb=8,
        )
        self.assertEqual(sess.get_resource_vector(), [1, 0, 8])

    def test_calculate_cost(self):
        start = timezone.now() - timezone.timedelta(minutes=60)
        sess = Session.objects.create(
            machine=self.machine, user=self.user,
            customer_name='Test', start_time=start,
            status='dang_chay', planned_minutes=60,
        )
        cost = sess.calculate_cost()
        # 60 phút × 10000/60 ≈ 10000
        self.assertAlmostEqual(float(cost), 10000, delta=500)