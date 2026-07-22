# app/scheduling_algorithms.py
"""
Hệ thống mô phỏng giải thuật lập lịch CPU và Banker Algorithm
cho Quán Net Mimi Lê

Ánh xạ thực tế:
  Khách hàng    → Tiến trình (Process)
  Giờ check-in  → Arrival Time
  Thời gian chơi → Burst Time
  Máy PC / Tai nghe / Tài khoản game → Tài nguyên hệ thống (Resources)
"""

import random
from django.utils import timezone


# ==============================================================
# TỔNG TÀI NGUYÊN HỆ THỐNG (chỉnh theo thực tế quán)
# ==============================================================
TOTAL_RESOURCES = {
    'headset': 8,      # Số tai nghe
    'account': 5,      # Số tài khoản game
    'ram_gb':  64,     # Tổng RAM khả dụng (GB)
}

RESOURCE_NAMES = ['Tai Nghe', 'Tài Khoản Game', 'RAM (GB)']


# ==============================================================
# HELPERS
# ==============================================================

def _build_task_list(process):
    """Tạo danh sách task cho Round Robin / OMDRRS từ process."""
    burst = max(1, int(process.get('burst', 1)))
    name = process.get('name', '')
    game_name = process.get('game_name') or process.get('activity') or 'game'
    tasks = []

    if burst <= 4:
        tasks.append({'name': 'Chuẩn bị và chơi', 'duration': burst})
        return tasks

    steps = [
        ('Chọn máy', 2),
        ('Chọn game', 1),
        ('Mua đồ ăn/uống', 1),
    ]
    remaining = burst
    for step_name, step_duration in steps:
        if remaining <= step_duration:
            tasks.append({'name': step_name, 'duration': remaining})
            remaining = 0
            break
        tasks.append({'name': step_name, 'duration': step_duration})
        remaining -= step_duration

    if remaining > 0:
        tasks.append({'name': f'Chơi {game_name}', 'duration': remaining})

    return tasks


def _compute_task_checklist(tasks, time_used_before, time_used_after):
    """
    Tính trạng thái task checklist trước và sau 1 slice CPU.
    tasks: list of {name, duration}
    time_used_before: tổng thời gian đã chạy TRƯỚC slice này
    time_used_after: tổng thời gian đã chạy SAU slice này
    Trả về (checklist_before, checklist_after)
    """
    def compute_state(time_used, tasks):
        result = []
        elapsed = 0
        for task in tasks:
            done = time_used > elapsed + task['duration'] - 1
            partial = not done and time_used > elapsed
            result.append({
                'name': task['name'],
                'duration': task['duration'],
                'done': done,
                'partial': partial,
            })
            elapsed += task['duration']
        return result

    return compute_state(time_used_before, tasks), compute_state(time_used_after, tasks)


def _normalize_process(process):
    proc = dict(process)
    proc['arrival'] = max(0, int(proc.get('arrival', 0)))
    proc['burst'] = max(1, int(proc.get('burst', 1)))
    proc.setdefault('priority', 3)
    proc.setdefault('state', 'ready')
    proc.setdefault('name', proc.get('name') or f"P{proc.get('pid', 0)}")
    proc.setdefault('customer_name', proc.get('customer_name') or proc.get('name'))
    proc.setdefault('machine', proc.get('machine', ''))
    proc.setdefault('tasks', _build_task_list(proc))
    proc['remaining'] = max(1, proc['burst'])
    proc['start_time'] = proc.get('start_time')
    proc['finish_time'] = proc.get('finish_time')
    return proc


def sessions_to_processes(sessions):
    """
    Chuyển danh sách Session (Django model) thành list dict tiến trình
    để đưa vào các giải thuật lập lịch.
    """
    processes = []
    for i, sess in enumerate(sessions):
        burst = sess.planned_minutes or max(1, sess.get_duration_minutes())
        remaining = sess.get_remaining_minutes() if sess.status == 'dang_chay' else burst
        arrival_dt = timezone.localtime(sess.start_time)
        processes.append({
            'pid':           i + 1,
            'session_id':    sess.id,
            'name':          f'P{i+1} — {sess.get_customer_name()}',
            'customer_name': sess.get_customer_name(),
            'machine':       sess.machine.name,
            'arrival':       int(sess.start_time.timestamp() // 60),
            'arrival_time':   arrival_dt.strftime('%H:%M'),
            'arrival_datetime': arrival_dt.isoformat(),
            'burst':         burst,
            'remaining':     remaining,
            'start_time':    sess.start_time.isoformat(),
            'finish_time':   sess.end_time.isoformat() if sess.end_time else '',
            'tasks':         _build_task_list({
                'burst': burst,
                'name': sess.get_game_name() if hasattr(sess, 'get_game_name') else sess.game_name,
                'game_name': sess.game_name,
            }),
            'state':         'running' if sess.status == 'dang_chay' else 'ready',
        })
    return [ _normalize_process(p) for p in processes ]


def queue_to_processes(queue_items):
    """Chuyển hàng chờ thành danh sách tiến trình"""
    processes = []
    for i, q in enumerate(queue_items):
        burst = q.planned_minutes or 60
        arrival_dt = timezone.localtime(q.arrived_at)
        processes.append(_normalize_process({
            'pid':          i + 1,
            'name':         f'P{i+1} — {q.customer_name}',
            'customer_name': q.customer_name,
            'machine':      '',
            'arrival':      int(q.arrived_at.timestamp() // 60),
            'arrival_time':  arrival_dt.strftime('%H:%M'),
            'arrival_datetime': arrival_dt.isoformat(),
            'burst':        burst,
            'remaining':    burst,
            'start_time':   '',
            'finish_time':  '',
            'tasks':        _build_task_list({'burst': burst, 'game_name': q.game_name if hasattr(q, 'game_name') else 'game'}),
            'state':        'ready',
        }))
    return processes


# ==============================================================
# 1. FCFS — First Come First Serve
# ==============================================================

def fcfs(processes):
    """
    Giải thuật FCFS: Khách đến trước phục vụ trước (không preemptive).
    Bổ sung: arrival_events, queue_state_names, decision_reason để mô phỏng quá trình quyết định.
    """
    if not processes:
        return []

    ps = sorted([dict(p) for p in processes], key=lambda p: (p['arrival'], p['pid']))
    timeline = []
    current_time = 0
    started = set()

    # Xây dựng arrival_events theo thứ tự thời gian
    arrival_events = sorted(
        [{'time': p['arrival'], 'name': p.get('name', f"P{p['pid']}"), 'pid': p['pid'],
          'customer_name': p.get('customer_name', p.get('name', f"KH{p['pid']}")),
          'arrival_time': p.get('arrival_time', ''),
          'arrival_display': p.get('arrival_display') or p.get('arrival_label') or f"t+{p['arrival']} phút"}
         for p in ps],
        key=lambda e: (e['time'], e['pid'])
    )

    for p in ps:
        if current_time < p['arrival']:
            current_time = p['arrival']
        # Process đã đến nhưng chưa chạy (không kể p hiện tại)
        ready_before_procs = [q for q in ps if q['arrival'] <= current_time and q['pid'] not in started and q['pid'] != p['pid']]
        ready_before = [q['pid'] for q in ready_before_procs]
        queue_state_names = [q.get('name', f"P{q['pid']}") for q in ready_before_procs]

        start = current_time
        end = start + p['burst']

        # Arrival events xảy ra trong cửa sổ [last_end, start]
        slice_arrivals = [e for e in arrival_events if e['time'] <= start and e['pid'] == p['pid']]

        if not ready_before:
            decision_reason = f"{p.get('name', f'P{p["pid"]}')} được chọn vì là tiến trình duy nhất sẵn sàng tại phút {start}."
        else:
            decision_reason = (f"{p.get('name', f'P{p["pid"]}')} được chọn theo thứ tự đến trước — "
                               f"Arrival = {p['arrival']} phút (sớm nhất trong queue).")

        timeline.append({
            **p,
            'start': start,
            'end': end,
            'wait': start - p['arrival'],
            'response': start - p['arrival'],
            'tat': end - p['arrival'],
            'ready_before': ready_before,
            'queue_state_names': queue_state_names,
            'arrival_events': arrival_events,
            'decision': decision_reason,
            'decision_reason': decision_reason,
            'quantum': None,
        })
        started.add(p['pid'])
        current_time = end

    return timeline


# ==============================================================
# 2. SJF — Shortest Job First (Non-preemptive)
# ==============================================================

def sjf(processes):
    """
    Giải thuật SJF: Tại mỗi thời điểm, chọn tiến trình sẵn có
    có burst time ngắn nhất (không preemptive).
    Bổ sung: sjf_comparison (bảng so sánh burst), decision_reason chi tiết.
    """
    if not processes:
        return []

    remaining = [dict(p) for p in processes]
    timeline = []
    current_time = 0
    completed = set()

    # Arrival events tổng
    arrival_events = sorted(
        [{'time': p['arrival'], 'name': p.get('name', f"P{p['pid']}"), 'pid': p['pid'],
          'customer_name': p.get('customer_name', p.get('name', f"KH{p['pid']}")),
          'arrival_time': p.get('arrival_time', ''),
          'arrival_display': p.get('arrival_display') or p.get('arrival_label') or f"t+{p['arrival']} phút"}
         for p in processes],
        key=lambda e: (e['time'], e['pid'])
    )

    while remaining:
        available = [p for p in remaining if p['arrival'] <= current_time]
        if not available:
            current_time = min(p['arrival'] for p in remaining)
            continue

        selected = min(available, key=lambda x: (x['burst'], x['arrival'], x['pid']))
        ready_before = [q['pid'] for q in available if q['pid'] != selected['pid']]
        queue_state_names = [q.get('name', f"P{q['pid']}") for q in available if q['pid'] != selected['pid']]

        # Sắp xếp available theo burst để xây dựng bảng so sánh
        sorted_available = sorted(available, key=lambda x: x['burst'])
        min_burst = selected['burst']
        sjf_comparison = []
        for rank, proc in enumerate(sorted_available, 1):
            sjf_comparison.append({
                'pid': proc['pid'],
                'name': proc.get('name', f"P{proc['pid']}"),
                'burst': proc['burst'],
                'rank': rank,
                'selected': proc['pid'] == selected['pid'],
                'reason': 'Burst nhỏ nhất → Được chọn!' if proc['pid'] == selected['pid']
                          else f"Burst lớn hơn {min_burst} phút",
            })

        start = current_time
        end = start + selected['burst']

        decision_reason = (
            f"{selected.get('name', f'P{selected["pid"]}')} được chọn vì "
            f"Burst Time = {selected['burst']} phút là nhỏ nhất trong Ready Queue."
        )
        if len(available) > 1:
            others = [f"{q.get('name', f'P{q["pid"]}')}(={q['burst']})"
                      for q in available if q['pid'] != selected['pid']]
            decision_reason += f" Các process khác: {', '.join(others)}."

        timeline.append({
            **selected,
            'start': start,
            'end': end,
            'wait': start - selected['arrival'],
            'response': start - selected['arrival'],
            'tat': end - selected['arrival'],
            'ready_before': ready_before,
            'queue_state_names': queue_state_names,
            'arrival_events': arrival_events,
            'sjf_comparison': sjf_comparison,
            'decision': decision_reason,
            'decision_reason': decision_reason,
            'quantum': None,
        })
        completed.add(selected['pid'])
        current_time = end
        remaining = [r for r in remaining if r['pid'] != selected['pid']]

    return timeline


# ==============================================================
# 3. ROUND ROBIN
# ==============================================================

def round_robin(processes, quantum=30):
    """
    Giải thuật Round Robin: mỗi tiến trình được chạy tối đa `quantum` phút,
    sau đó nhường chỗ cho tiến trình tiếp theo trong hàng chờ.
    Bổ sung: task_checklist_before/after, queue_after_names, quantum_expired.
    """
    if not processes:
        return []

    ps = sorted([dict(p, rem=p['burst']) for p in processes], key=lambda x: (x['arrival'], x['pid']))
    queue = []
    timeline = []
    first_start = {}
    last_end = {}
    current_time = 0
    idx = 0
    time_used_map = {}  # pid -> tổng thời gian đã chạy

    # Arrival events tổng
    arrival_events = sorted(
        [{'time': p['arrival'], 'name': p.get('name', f"P{p['pid']}"), 'pid': p['pid'],
          'customer_name': p.get('customer_name', p.get('name', f"KH{p['pid']}")),
          'arrival_time': p.get('arrival_time', ''),
          'arrival_display': p.get('arrival_display') or p.get('arrival_label') or f"t+{p['arrival']} phút"}
         for p in processes],
        key=lambda e: (e['time'], e['pid'])
    )

    while idx < len(ps) or queue:
        while idx < len(ps) and ps[idx]['arrival'] <= current_time:
            queue.append(ps[idx])
            idx += 1

        if not queue:
            current_time = ps[idx]['arrival']
            continue

        p = queue.pop(0)
        ready_before = [q['pid'] for q in queue]
        ready_before_names = [q.get('name', f"P{q['pid']}") for q in queue]
        slice_time = min(quantum, p['rem'])
        start = current_time
        end = start + slice_time
        if p['pid'] not in first_start:
            first_start[p['pid']] = start

        remaining_before = p['rem']
        time_used_before = time_used_map.get(p['pid'], 0)
        time_used_after = time_used_before + slice_time
        time_used_map[p['pid']] = time_used_after

        # Tính task checklist
        tasks = p.get('tasks', [])
        task_checklist_before, task_checklist_after = _compute_task_checklist(
            tasks, time_used_before, time_used_after
        )

        p['rem'] -= slice_time
        current_time = end

        while idx < len(ps) and ps[idx]['arrival'] <= current_time:
            queue.append(ps[idx])
            idx += 1

        quantum_expired = p['rem'] > 0
        if quantum_expired:
            queue.append(p)
            queue_after = [q['pid'] for q in queue]
            queue_after_names = [q.get('name', f"P{q['pid']}") for q in queue]
        else:
            last_end[p['pid']] = end
            queue_after = [q['pid'] for q in queue]
            queue_after_names = [q.get('name', f"P{q['pid']}") for q in queue]

        if quantum_expired:
            decision = (f"{p.get('name', f'P{p["pid"]}')} chạy {slice_time} phút "
                        f"(quantum = {quantum}). Hết quantum! "
                        f"Còn {p['rem']} phút → Đưa xuống cuối queue.")
        else:
            decision = (f"{p.get('name', f'P{p["pid"]}')} hoàn thành sau {slice_time} phút. "
                        f"Burst time {p['burst']} phút đã hết.")

        timeline.append({
            **p,
            'start': start,
            'end': end,
            'wait': first_start[p['pid']] - p['arrival'],
            'response': first_start[p['pid']] - p['arrival'],
            'tat': (last_end.get(p['pid'], end)) - p['arrival'],
            'remaining_before': remaining_before,
            'remaining_after': p['rem'],
            'ready_before': ready_before,
            'ready_before_names': ready_before_names,
            'queue_after': queue_after,
            'queue_after_names': queue_after_names,
            'quantum_expired': quantum_expired,
            'task_checklist_before': task_checklist_before,
            'task_checklist_after': task_checklist_after,
            'arrival_events': arrival_events,
            'decision': decision,
            'decision_reason': decision,
            'quantum': quantum,
        })

    return timeline


# ==============================================================
# 4. BANKER ALGORITHM — Safety Check & Resource Allocation
# ==============================================================

def build_banker_data(active_sessions):
    """
    Xây dựng dữ liệu đầu vào cho Banker Algorithm từ các phiên đang chạy.

    Tài nguyên: [headset, account, ram_gb]
    Total      = TOTAL_RESOURCES (cố định)
    Allocation = tài nguyên mỗi phiên đang dùng
    Max        = tài nguyên tối đa mỗi phiên cần (= allocation vì đã cấp rồi)
    Available  = Total - sum(Allocation)
    Need       = Max - Allocation

    Returns:
        dict với keys: n, m, resource_names, total, available, allocation, max_need, need
    """
    total = [
        TOTAL_RESOURCES['headset'],
        TOTAL_RESOURCES['account'],
        TOTAL_RESOURCES['ram_gb'],
    ]

    allocation = [sess.get_resource_vector() for sess in active_sessions]
    max_need   = [list(row) for row in allocation]  # max = đang dùng

    m = len(total)
    n = len(allocation)

    # Tổng đang dùng
    used = [sum(allocation[i][j] for i in range(n)) for j in range(m)]
    available = [max(0, total[j] - used[j]) for j in range(m)]

    # Need = Max - Allocation (ở đây = 0 vì max = allocation)
    need = [[max_need[i][j] - allocation[i][j] for j in range(m)] for i in range(n)]

    return {
        'n':              n,
        'm':              m,
        'resource_names': RESOURCE_NAMES,
        'total':          total,
        'available':      available,
        'allocation':     allocation,
        'max_need':       max_need,
        'need':           need,
    }


def banker_safety(n, available, allocation, need, session_names=None):
    """
    Thuật toán kiểm tra trạng thái an toàn (Safety Algorithm).

    Bước:
        1. Work = Available, Finish[i] = False
        2. Tìm i: Finish[i]=False AND Need[i] <= Work
        3. Work += Allocation[i], Finish[i] = True
        4. Lặp đến khi không tìm được i nào
        5. Nếu tất cả Finish=True → An toàn

    Returns:
        dict:
            safe        : bool
            safe_sequence: list[int] — thứ tự index tiến trình an toàn
            trace       : list[dict] — chi tiết từng bước
            deadlock_info: dict — thông tin deadlock nếu có
    """
    work   = list(available)
    finish = [False] * n
    seq    = []
    trace  = []
    deadlock_info = {
        'is_deadlock': False,
        'blocked_processes': [],
        'reason': '',
        'solution': '',
        'deadlock_log': [],
    }

    changed = True
    while changed:
        changed = False
        for i in range(n):
            if not finish[i] and all(need[i][j] <= work[j] for j in range(len(work))):
                work_before = list(work)
                work = [work[j] + allocation[i][j] for j in range(len(work))]
                finish[i] = True
                seq.append(i)
                trace.append({
                    'step':         len(trace) + 1,
                    'proc_index':   i,
                    'need':         list(need[i]),
                    'work_before':  work_before,
                    'work_after':   list(work),
                    'result':       'OK',
                })
                changed = True

    # Kiểm tra deadlock
    if not all(finish):
        blocked = [i for i in range(n) if not finish[i]]
        blocked_names = []
        for i in blocked:
            name = session_names[i] if session_names and i < len(session_names) else f'Tiến trình P{i}'
            blocked_names.append(name)
        
        # Tạo log deadlock chi tiết
        deadlock_log = []
        deadlock_log.append("=" * 60)
        deadlock_log.append("⚠️  PHÁT HIỆN DEADLOCK (BẾ TẮC)!")
        deadlock_log.append("=" * 60)
        deadlock_log.append(f"Tổng số tiến trình: {n}")
        deadlock_log.append(f"Số tiến trình bị chặn: {len(blocked)}")
        deadlock_log.append(f"Số tiến trình hoàn thành: {len(seq)}")
        deadlock_log.append("")
        deadlock_log.append("--- DANH SÁCH TIẾN TRÌNH BỊ CHẶN ---")
        
        for i in blocked:
            name = session_names[i] if session_names and i < len(session_names) else f'P{i}'
            need_str = ', '.join([f'{RESOURCE_NAMES[j]}: {need[i][j]}' for j in range(len(need[i]))])
            alloc_str = ', '.join([f'{RESOURCE_NAMES[j]}: {allocation[i][j]}' for j in range(len(allocation[i]))])
            deadlock_log.append(f"  • {name}:")
            deadlock_log.append(f"    - Đã cấp (Allocation): [{alloc_str}]")
            deadlock_log.append(f"    - Cần thêm (Need): [{need_str}]")
        
        deadlock_log.append("")
        deadlock_log.append("--- TÀI NGUYÊN HIỆN TẠI ---")
        avail_str = ', '.join([f'{RESOURCE_NAMES[j]}: {work[j]}' for j in range(len(work))])
        deadlock_log.append(f"  Work (Available còn lại): [{avail_str}]")
        deadlock_log.append("")
        
        # Giải thích lý do deadlock
        deadlock_log.append("--- NGUYÊN NHÂN DEADLOCK ---")
        deadlock_reason_parts = []
        for i in blocked:
            name = session_names[i] if session_names and i < len(session_names) else f'P{i}'
            need_str_parts = [f'{RESOURCE_NAMES[j]}={need[i][j]}' for j in range(len(need[i])) if need[i][j] > 0]
            if need_str_parts:
                deadlock_reason_parts.append(f"{name} cần thêm {', '.join(need_str_parts)}")
        deadlock_log.append(f"  Các tiến trình sau không thể hoàn thành vì tài nguyên không đủ:")
        for part in deadlock_reason_parts:
            deadlock_log.append(f"    • {part}")
        deadlock_log.append(f"  Work hiện tại [{', '.join(map(str, work))}] không đủ để đáp ứng nhu cầu của bất kỳ tiến trình bị chặn nào.")
        deadlock_log.append("")
        
        # Đề xuất giải pháp
        deadlock_log.append("--- CÁCH XỬ LÝ DEADLOCK ---")
        deadlock_log.append("  Giải pháp 1: Kết thúc (Terminate) một số tiến trình để giải phóng tài nguyên.")
        deadlock_log.append("  Giải pháp 2: Thu hồi tài nguyên (Preemption) từ các tiến trình đang chạy.")
        deadlock_log.append("  Giải pháp 3: Chờ một số tiến trình hoàn thành tự nhiên.")
        deadlock_log.append("")
        
        # Đề xuất cụ thể
        deadlock_log.append("--- ĐỀ XUẤT CỤ THỂ ---")
        # Tìm tiến trình có allocation nhỏ nhất để terminate
        if blocked:
            min_alloc_idx = min(blocked, key=lambda i: sum(allocation[i]))
            min_name = session_names[min_alloc_idx] if session_names and min_alloc_idx < len(session_names) else f'P{min_alloc_idx}'
            deadlock_log.append(f"  • Nên kết thúc {min_name} (tốn ít tài nguyên nhất) để giải phóng tài nguyên.")
            deadlock_log.append(f"  • Hoặc chờ các tiến trình đã hoàn thành (P{', P'.join(map(str, seq))}) giải phóng tài nguyên.")
        
        deadlock_log.append("")
        deadlock_log.append("=" * 60)
        
        deadlock_info = {
            'is_deadlock': True,
            'blocked_processes': blocked,
            'blocked_names': blocked_names,
            'reason': f"Các tiến trình {', '.join(blocked_names)} bị chặn do không đủ tài nguyên. Work={work} không đáp ứng được Need của bất kỳ tiến trình nào.",
            'solution': f"1) Kết thúc tiến trình để giải phóng tài nguyên.\n2) Thu hồi tài nguyên từ tiến trình khác.\n3) Chờ tiến trình khác hoàn thành.",
            'deadlock_log': deadlock_log,
        }

    return {
        'safe':          all(finish),
        'safe_sequence': seq,
        'trace':         trace,
        'deadlock_info': deadlock_info,
    }


def banker_request(request_vector, session_index, banker_data):
    """
    Kiểm tra yêu cầu tài nguyên mới có được cấp phát an toàn không.

    Args:
        request_vector: list[int]  — tài nguyên muốn xin thêm
        session_index:  int        — chỉ số phiên trong banker_data
        banker_data:    dict       — kết quả của build_banker_data()

    Returns:
        dict:
            can_grant : bool
            reason    : str
            safe_after: bool — nếu cấp thì có an toàn không
            sequence  : list[int]
    """
    avail  = list(banker_data['available'])
    alloc  = [list(row) for row in banker_data['allocation']]
    need   = [list(row) for row in banker_data['need']]
    n      = banker_data['n']
    m      = banker_data['m']

    # Kiểm tra Request <= Need[i]
    if any(request_vector[j] > need[session_index][j] for j in range(m)):
        return {
            'can_grant': False,
            'reason':    'Yêu cầu vượt quá mức tối đa đã khai báo (Request > Need).',
            'safe_after': False,
            'sequence':   [],
        }

    # Kiểm tra Request <= Available
    if any(request_vector[j] > avail[j] for j in range(m)):
        return {
            'can_grant': False,
            'reason':    'Không đủ tài nguyên khả dụng (Request > Available). Tiến trình phải chờ.',
            'safe_after': False,
            'sequence':   [],
        }

    # Giả sử cấp phát, kiểm tra an toàn
    avail_new = [avail[j] - request_vector[j] for j in range(m)]
    alloc_new = [list(row) for row in alloc]
    need_new  = [list(row) for row in need]
    alloc_new[session_index] = [alloc[session_index][j] + request_vector[j] for j in range(m)]
    need_new[session_index]  = [need[session_index][j]  - request_vector[j] for j in range(m)]

    result = banker_safety(n, avail_new, alloc_new, need_new)

    return {
        'can_grant':  result['safe'],
        'reason':     'Trạng thái an toàn sau khi cấp phát.' if result['safe']
                      else 'Cấp phát sẽ dẫn đến trạng thái không an toàn (deadlock)!',
        'safe_after': result['safe'],
        'sequence':   result['safe_sequence'],
    }


# ==============================================================
# THỐNG KÊ KẾT QUẢ LẬP LỊCH
# ==============================================================

def renumber_processes(processes):
    """Gán lại pid tuần tự cho danh sách tiến trình."""
    for index, proc in enumerate(processes, start=1):
        proc['pid'] = index
    return processes


def normalize_arrival_times(processes):
    """Chuyen arrival time ve moc phut tuong doi tu tien trinh den dau tien."""
    if not processes:
        return processes

    min_arrival = min(int(proc.get('arrival', 0)) for proc in processes)
    for proc in processes:
        original_arrival = int(proc.get('arrival', 0))
        proc['original_arrival'] = original_arrival
        proc['arrival'] = max(0, original_arrival - min_arrival)
        relative_label = f"t+{proc['arrival']} phút"
        proc['arrival_label'] = relative_label
        proc['arrival_display'] = (
            f"{proc['arrival_time']} ({relative_label})"
            if proc.get('arrival_time')
            else relative_label
        )
    return processes


def generate_random_processes(count, arrival_max=10, burst_min=5, burst_max=30, seed=None):
    """Sinh bộ tiến trình ngẫu nhiên phục vụ mô phỏng."""
    import random
    rng = random.Random(seed) if seed else random.Random()
    processes = []
    for i in range(max(1, count)):
        burst = rng.randint(max(1, burst_min), max(burst_min, burst_max))
        name = f'P{i + 1}'
        process = {
            'pid': i + 1,
            'name': name,
            'arrival': rng.randint(0, max(0, arrival_max)),
            'burst': burst,
            'priority': rng.randint(1, 5),
            'tasks': _build_task_list({'burst': burst, 'name': name, 'game_name': 'Game'}),
        }
        processes.append(process)
    return processes


def build_scheduling_events(timeline, algorithm='fcfs', quantum=30):
    """Chuyển timeline thành các bước mô phỏng có mô tả tự nhiên.
    Bổ sung đầy đủ dữ liệu cho giao diện mô phỏng từng bước.
    """
    events = []
    for index, seg in enumerate(timeline, start=1):
        duration = max(0, seg['end'] - seg['start'])
        name = seg.get('name', f"P{seg.get('pid', index)}")
        ready = seg.get('ready_before', [])
        queue_after = seg.get('queue_after', [])
        decision = seg.get('decision') or seg.get('decision_reason', '')

        if algorithm == 'rr':
            message = decision or (
                f"{name} được cấp CPU trong {duration} phút "
                f"(quantum = {seg.get('quantum', quantum)} phút)."
            )
        elif algorithm == 'sjf':
            message = decision or (
                f"{name} được chọn vì có Burst Time ngắn nhất trong Ready Queue tại thời điểm {seg['start']} phút."
            )
        elif algorithm == 'omdrrs':
            message = decision or (
                f"{name} được chọn bởi OMDRRS với quantum động {seg.get('quantum', 0)}."
            )
        else:
            message = decision or (
                f"{name} được phục vụ theo thứ tự đến (FCFS), chạy từ {seg['start']} đến {seg['end']} phút."
            )

        events.append({
            'step': index,
            'pid': seg['pid'],
            'name': name,
            'burst': seg.get('burst', 0),
            'arrival': seg.get('arrival', 0),
            'customer_name': seg.get('customer_name', name),
            'start': seg['start'],
            'end': seg['end'],
            'duration': duration,
            'message': message,
            'decision_reason': seg.get('decision_reason', message),
            'quantum': seg.get('quantum'),
            # Ready queue
            'ready_before': ready,
            'ready_before_names': seg.get('ready_before_names', [seg.get('name', f"P{pid}")
                                           for pid in ready]),
            'queue_state_names': seg.get('queue_state_names', []),
            # After queue
            'queue_after': queue_after,
            'queue_after_names': seg.get('queue_after_names', []),
            # RR-specific
            'remaining_before': seg.get('remaining_before'),
            'remaining_after': seg.get('remaining_after'),
            'quantum_expired': seg.get('quantum_expired', False),
            'task_checklist_before': seg.get('task_checklist_before', []),
            'task_checklist_after': seg.get('task_checklist_after', []),
            # SJF-specific
            'sjf_comparison': seg.get('sjf_comparison', []),
            # OMDRRS-specific
            'f_values': seg.get('f_values', seg.get('f_values_snapshot', [])),
            'round_number': seg.get('round_number', index),
            'quantum_new': seg.get('quantum_new', seg.get('quantum')),
            'quantum_reason': seg.get('quantum_reason', ''),
            'avg_remaining_burst': seg.get('avg_remaining_burst', 0),
            # Timeline
            'arrival_events': seg.get('arrival_events', []),
        })
    return events


ALGORITHM_DESCRIPTIONS = {
    'fcfs': (
        'Tiến trình đến trước được CPU phục vụ trước. Dễ triển khai, phù hợp demo live, '
        'nhưng có thể làm tăng waiting time khi job dài đến sớm.'
    ),
    'sjf': (
        'Luôn ưu tiên tiến trình có burst time ngắn nhất trong ready queue. '
        'Waiting time trung bình thường tốt hơn FCFS nhưng có nguy cơ starvation.'
    ),
    'rr': (
        'Mỗi tiến trình chỉ giữ CPU tối đa một quantum rồi nhường cho tiến trình kế tiếp. '
        'Công bằng, phản hồi nhanh, phù hợp hệ thống tương tác.'
    ),
    'qlearning': (
        'Reinforcement learning (Q-Learning): agent học chọn tiến trình trong Ready Queue '
        'dựa trên Q-table, tối ưu reward (giảm chờ, giảm context switch).'
    ),
}


def count_context_switches(timeline):
    """Đếm số lần CPU chuyển sang tiến trình khác (giữa các segment liên tiếp)."""
    if not timeline:
        return 0
    count = 0
    last_pid = None
    for seg in timeline:
        pid = seg.get('pid')
        if last_pid is not None and pid != last_pid:
            count += 1
        last_pid = pid
    return count


def calc_stats(timeline, processes):
    """
    Tính các chỉ số hiệu suất từ timeline.

    Returns:
        dict: avg_wait, avg_tat, avg_response, cpu_util (%)
    """
    if not timeline or not processes:
        return {'avg_wait': 0, 'avg_tat': 0, 'avg_response': 0, 'cpu_util': 0}

    process_map = {p['pid']: p for p in processes}
    first_start = {}
    completion = {}
    for seg in timeline:
        pid = seg['pid']
        first_start[pid] = min(first_start.get(pid, seg['start']), seg['start'])
        completion[pid] = max(completion.get(pid, seg['end']), seg['end'])

    stats_by_pid = {}
    for pid, finish in completion.items():
        proc = process_map.get(pid, {})
        arrival = proc.get('arrival', 0)
        burst = proc.get('burst', 0)
        tat = finish - arrival
        stats_by_pid[pid] = {
            'wait': max(0, tat - burst),
            'tat': tat,
            'response': max(0, first_start[pid] - arrival),
        }

    n = len(stats_by_pid)
    avg_wait = round(sum(v['wait'] for v in stats_by_pid.values()) / n, 1)
    avg_tat  = round(sum(v['tat']  for v in stats_by_pid.values()) / n, 1)
    avg_response = round(sum(v['response'] for v in stats_by_pid.values()) / n, 1)

    total_burst = sum(p['burst'] for p in processes)
    max_end     = max(seg['end'] for seg in timeline)
    min_arrival = min(p['arrival'] for p in processes)
    span        = max_end - min_arrival
    cpu_util    = round(min(100, total_burst / span * 100), 1) if span > 0 else 100.0

    return {
        'avg_wait': avg_wait,
        'avg_tat':  avg_tat,
        'avg_response': avg_response,
        'cpu_util': cpu_util,
    }


# ==============================================================
# 5. DBDAA — Dynamic Banker's Deadlock Avoidance Algorithm
# ==============================================================

def dbdaa_safety(n, available, allocation, need, session_names=None):
    """
    Thuật toán DBDAA - Dynamic Banker's Deadlock Avoidance Algorithm
    
    Cải tiến từ Banker truyền thống với:
    - Sắp xếp dựa trên nhu cầu (Sorted Ready Queue - SRQ)
    - Kiểm tra nhanh (Fast-track Check)
    - Cơ chế danh sách chờ (Primary Unsafe Sequence)
    
    Độ phức tạp: O(nd) thay vì O(n²d) của Banker truyền thống
    
    Args:
        n: số tiến trình
        available: list[int] - tài nguyên khả dụng
        allocation: list[list[int]] - ma trận cấp phát
        need: list[list[int]] - ma trận nhu cầu
        session_names: list[str] - tên các phiên/tiến trình
    
    Returns:
        dict:
            safe: bool - trạng thái an toàn
            safe_sequence: list[int] - thứ tự an toàn
            trace: list[dict] - chi tiết từng bước
            primary_unsafe: list[int] - danh sách chờ unsafe
            deadlock_info: dict - thông tin deadlock nếu có
            performance: dict - thông tin hiệu suất
    """
    # Xử lý trường hợp không có tiến trình
    if n == 0:
        return {
            'safe': True,
            'safe_sequence': [],
            'trace': [],
            'primary_unsafe': [],
            'deadlock_info': {
                'is_deadlock': False,
                'blocked_processes': [],
                'reason': '',
                'solution': '',
                'deadlock_log': [],
            },
            'performance': {
                'total_comparisons': 0,
                'fast_track_skips': 0,
                'srq_reorderings': 0,
            },
        }
    
    work = list(available)
    finish = [False] * n
    seq = []
    trace = []
    primary_unsafe = []
    performance = {
        'total_comparisons': 0,
        'fast_track_skips': 0,
        'srq_reorderings': 0,
    }
    
    deadlock_info = {
        'is_deadlock': False,
        'blocked_processes': [],
        'reason': '',
        'solution': '',
        'deadlock_log': [],
    }
    
    # Bước 1: Tính Max_Need cho mỗi tiến trình (tổng nhu cầu)
    max_need_values = []
    for i in range(n):
        max_need = sum(need[i])
        max_need_values.append((i, max_need))
    
    # Bước 2: Sắp xếp theo Max_Need tăng dần (SRQ - Sorted Ready Queue)
    sorted_indices = [idx for idx, _ in sorted(max_need_values, key=lambda x: x[1])]
    performance['srq_reorderings'] = 1
    
    # Bước 3: Tính Min_A (giá trị tài nguyên khả dụng nhỏ nhất)
    min_a = min(work) if work else 0
    
    # Bước 4: Kiểm tra an toàn với SRQ và Fast-track Check
    changed = True
    iteration = 0
    
    while changed:
        changed = False
        iteration += 1
        
        # Duyệt theo thứ tự đã sắp xếp
        for i in sorted_indices:
            if finish[i]:
                continue
            
            performance['total_comparisons'] += 1
            
            # Fast-track Check: so sánh Max_Need với Min_A
            current_max_need = sum(need[i])
            if current_max_need > min_a:
                # Bỏ qua kiểm tra sâu, đưa vào primary_unsafe
                if i not in primary_unsafe:
                    primary_unsafe.append(i)
                    performance['fast_track_skips'] += 1
                
                # Ghi lại bước fast-track skip
                trace.append({
                    'step': len(trace) + 1,
                    'proc_index': i,
                    'proc_name': session_names[i] if session_names and i < len(session_names) else f'P{i}',
                    'max_need': current_max_need,
                    'need': list(need[i]),
                    'work_before': list(work),
                    'work_after': list(work),
                    'min_a': min_a,
                    'fast_track': 'SKIP',
                    'result': 'UNSAFE',
                })
                continue
            
            # Kiểm tra sâu: Need <= Work
            if all(need[i][j] <= work[j] for j in range(len(work))):
                work_before = list(work)
                work = [work[j] + allocation[i][j] for j in range(len(work))]
                finish[i] = True
                seq.append(i)
                
                # Xóa khỏi primary_unsafe nếu có
                if i in primary_unsafe:
                    primary_unsafe.remove(i)
                
                trace.append({
                    'step': len(trace) + 1,
                    'proc_index': i,
                    'proc_name': session_names[i] if session_names and i < len(session_names) else f'P{i}',
                    'max_need': current_max_need,
                    'need': list(need[i]),
                    'work_before': work_before,
                    'work_after': list(work),
                    'min_a': min_a,
                    'fast_track': 'PASS',
                    'result': 'OK',
                })
                changed = True
                
                # Cập nhật Min_A sau khi thay đổi Work
                min_a = min(work) if work else 0
            else:
                # Ghi lại bước kiểm tra thất bại
                trace.append({
                    'step': len(trace) + 1,
                    'proc_index': i,
                    'proc_name': session_names[i] if session_names and i < len(session_names) else f'P{i}',
                    'max_need': current_max_need,
                    'need': list(need[i]),
                    'work_before': list(work),
                    'work_after': list(work),
                    'min_a': min_a,
                    'fast_track': 'PASS',
                    'result': 'WAIT',
                })
    
    # Kiểm tra deadlock
    if not all(finish):
        blocked = [i for i in range(n) if not finish[i]]
        blocked_names = []
        for i in blocked:
            name = session_names[i] if session_names and i < len(session_names) else f'Tiến trình P{i}'
            blocked_names.append(name)
        
        # Tạo log deadlock chi tiết
        deadlock_log = []
        deadlock_log.append("=" * 60)
        deadlock_log.append("⚠️  PHÁT HIỆN DEADLOCK (BẾ TẮC) - DBDAA!")
        deadlock_log.append("=" * 60)
        deadlock_log.append(f"Tổng số tiến trình: {n}")
        deadlock_log.append(f"Số tiến trình hoàn thành: {len(seq)}")
        deadlock_log.append(f"Số tiến trình trong Primary Unsafe: {len(primary_unsafe)}")
        deadlock_log.append(f"Số tiến trình bị chặn: {len(blocked)}")
        deadlock_log.append("")
        deadlock_log.append("--- DANH SÁCH PRIMARY UNSAFE SEQUENCE ---")
        
        for i in primary_unsafe:
            name = session_names[i] if session_names and i < len(session_names) else f'P{i}'
            need_str = ', '.join([f'{RESOURCE_NAMES[j]}: {need[i][j]}' for j in range(len(need[i]))])
            alloc_str = ', '.join([f'{RESOURCE_NAMES[j]}: {allocation[i][j]}' for j in range(len(allocation[i]))])
            deadlock_log.append(f"  • {name}:")
            deadlock_log.append(f"    - Max_Need: {sum(need[i])}")
            deadlock_log.append(f"    - Đã cấp (Allocation): [{alloc_str}]")
            deadlock_log.append(f"    - Cần thêm (Need): [{need_str}]")
        
        deadlock_log.append("")
        deadlock_log.append("--- TÀI NGUYÊN HIỆN TẠI ---")
        avail_str = ', '.join([f'{RESOURCE_NAMES[j]}: {work[j]}' for j in range(len(work))])
        deadlock_log.append(f"  Work (Available): [{avail_str}]")
        deadlock_log.append(f"  Min_A (tài nguyên nhỏ nhất): {min_a}")
        deadlock_log.append("")
        
        deadlock_log.append("--- HIỆU SUẤT DBDAA ---")
        deadlock_log.append(f"  Tổng số phép so sánh: {performance['total_comparisons']}")
        deadlock_log.append(f"  Số lần Fast-track skip: {performance['fast_track_skips']}")
        deadlock_log.append(f"  Tỷ lệ skip: {performance['fast_track_skips'] / performance['total_comparisons'] * 100:.1f}%")
        deadlock_log.append("")
        
        deadlock_info = {
            'is_deadlock': True,
            'blocked_processes': blocked,
            'blocked_names': blocked_names,
            'primary_unsafe': primary_unsafe,
            'reason': f"Các tiến trình {', '.join(blocked_names)} bị chặn. DBDAA đã đưa {len(primary_unsafe)} tiến trình vào Primary Unsafe Sequence.",
            'solution': "DBDAA sẽ giữ các tiến trình trong Primary Unsafe và kiểm tra lại khi tài nguyên được giải phóng.",
            'deadlock_log': deadlock_log,
        }
    
    return {
        'safe': all(finish),
        'safe_sequence': seq,
        'trace': trace,
        'primary_unsafe': primary_unsafe,
        'deadlock_info': deadlock_info,
        'performance': performance,
    }


def dbdaa_request(request_vector, session_index, banker_data):
    """
    Kiểm tra yêu cầu tài nguyên mới với DBDAA
    
    Args:
        request_vector: list[int] - tài nguyên muốn xin thêm
        session_index: int - chỉ số phiên trong banker_data
        banker_data: dict - kết quả của build_banker_data()
    
    Returns:
        dict:
            can_grant: bool
            reason: str
            safe_after: bool
            sequence: list[int]
            performance: dict
    """
    avail = list(banker_data['available'])
    alloc = [list(row) for row in banker_data['allocation']]
    need = [list(row) for row in banker_data['need']]
    n = banker_data['n']
    m = banker_data['m']
    
    # Kiểm tra Request <= Need[i]
    if any(request_vector[j] > need[session_index][j] for j in range(m)):
        return {
            'can_grant': False,
            'reason': 'Yêu cầu vượt quá mức tối đa đã khai báo (Request > Need).',
            'safe_after': False,
            'sequence': [],
            'performance': {},
        }
    
    # Kiểm tra Request <= Available
    if any(request_vector[j] > avail[j] for j in range(m)):
        return {
            'can_grant': False,
            'reason': 'Không đủ tài nguyên khả dụng (Request > Available). Tiến trình phải chờ.',
            'safe_after': False,
            'sequence': [],
            'performance': {},
        }
    
    # Giả sử cấp phát, kiểm tra an toàn với DBDAA
    avail_new = [avail[j] - request_vector[j] for j in range(m)]
    alloc_new = [list(row) for row in alloc]
    need_new = [list(row) for row in need]
    alloc_new[session_index] = [alloc[session_index][j] + request_vector[j] for j in range(m)]
    need_new[session_index] = [need[session_index][j] - request_vector[j] for j in range(m)]
    
    result = dbdaa_safety(n, avail_new, alloc_new, need_new)
    
    return {
        'can_grant': result['safe'],
        'reason': 'Trạng thái an toàn sau khi cấp phát (DBDAA).' if result['safe']
                  else 'Cấp phát sẽ dẫn đến trạng thái không an toàn (DBDAA)!',
        'safe_after': result['safe'],
        'sequence': result['safe_sequence'],
        'performance': result['performance'],
    }


# ==============================================================
# 6. Q-LEARNING - AQSA (Adaptive Workload Management and Resource Scheduling Algorithm)
# ==============================================================

class AQSAExperienceReplay:
    """
    Experience Replay Buffer cho AQSA
    Lưu trữ các trải nghiệm (state, action, reward, next_state) để huấn luyện lại
    """
    def __init__(self, capacity=10000):
        self.capacity = capacity
        self.buffer = []
        self.position = 0
    
    def push(self, state, action, reward, next_state):
        """Thêm trải nghiệm mới vào buffer"""
        if len(self.buffer) < self.capacity:
            self.buffer.append(None)
        self.buffer[self.position] = (state, action, reward, next_state)
        self.position = (self.position + 1) % self.capacity
    
    def sample(self, batch_size):
        """Lấy mẫu ngẫu nhiên từ buffer"""
        return random.sample(self.buffer, min(batch_size, len(self.buffer)))
    
    def __len__(self):
        return len(self.buffer)


class AQSAAdamW:
    """
    AdamW Optimizer đơn giản cho AQSA
    Sử dụng weight decay để ngăn chặn overfitting
    """
    def __init__(self, learning_rate=0.0001, weight_decay=0.01):
        self.learning_rate = learning_rate
        self.weight_decay = weight_decay
        self.m = {}  # First moment
        self.v = {}  # Second moment
        self.t = 0   # Time step
        self.beta1 = 0.9
        self.beta2 = 0.999
        self.epsilon = 1e-8
    
    def update(self, params, grads):
        """
        Cập nhật tham số sử dụng AdamW
        params: dict của tham số cần cập nhật
        grads: dict của gradient tương ứng
        """
        self.t += 1
        
        for key in params:
            if key not in self.m:
                self.m[key] = 0
                self.v[key] = 0
            
            # First moment estimate
            self.m[key] = self.beta1 * self.m[key] + (1 - self.beta1) * grads[key]
            # Second moment estimate
            self.v[key] = self.beta2 * self.v[key] + (1 - self.beta2) * (grads[key] ** 2)
            
            # Bias correction
            m_hat = self.m[key] / (1 - self.beta1 ** self.t)
            v_hat = self.v[key] / (1 - self.beta2 ** self.t)
            
            # Update with weight decay
            params[key] = params[key] - self.learning_rate * (m_hat / (v_hat ** 0.5 + self.epsilon) + self.weight_decay * params[key])
        
        return params


class AQSAgent:
    """
    AQSA (Adaptive Workload Management and Resource Scheduling Algorithm based on Q-learning)
    Học cách quản lý khối lượng công việc thích ứng và lập lịch tài nguyên
    """
    def __init__(self, learning_rate=0.0001, discount_factor=0.99, epsilon=0.1, weight_decay=0.01):
        self.learning_rate = learning_rate
        self.discount_factor = discount_factor
        self.epsilon = epsilon
        self.weight_decay = weight_decay
        self.q_table = {}
        self.episode_rewards = []
        self.episode_steps = []
        self.replay_buffer = AQSAExperienceReplay(capacity=10000)
        self.optimizer = AQSAAdamW(learning_rate=learning_rate, weight_decay=weight_decay)
    
    def get_state_key(self, cpu_util, memory_usage, queue_length):
        """
        Tạo key cho state đa chiều theo mô hình AQSA
        State bao gồm: CPU utilization, Memory usage, Task queue length
        """
        # Rounding để giảm số lượng state
        cpu_rounded = round(cpu_util, 2)
        memory_rounded = round(memory_usage, 2)
        queue_rounded = min(queue_length, 20)  # Giới hạn tối đa 20
        
        return (cpu_rounded, memory_rounded, queue_rounded)
    
    def get_action(self, state_key, n_actions):
        """
        Chọn action: epsilon-greedy policy
        Actions: 0=Giảm độ ưu tiên, 1=Giữ nguyên, 2=Tăng độ ưu tiên, 3=Cấp phát thêm tài nguyên
        """
        if state_key not in self.q_table:
            self.q_table[state_key] = [0.0] * n_actions
        
        # Epsilon-greedy: khám phá với xác suất epsilon
        if random.random() < self.epsilon:
            return random.randint(0, n_actions - 1)
        
        # Chọn action có Q-value cao nhất
        return self.q_table[state_key].index(max(self.q_table[state_key]))
    
    def calculate_reward(self, cpu_util, memory_usage, queue_length):
        """
        Tính reward theo mô hình AQSA: rt = - (CPUt + Memoryt + QueueLengtht)
        Reward càng cao (ít âm) khi hệ thống ít tải
        """
        return - (cpu_util + memory_usage + queue_length)
    
    def update_q_value(self, state_key, action, reward, next_state_key):
        """
        Cập nhật Q-value theo công thức Q-learning
        Q(s,a) = Q(s,a) + alpha * [r + gamma * max(Q(s',a')) - Q(s,a)]
        """
        if state_key not in self.q_table:
            self.q_table[state_key] = [0.0] * len(self.q_table.get(next_state_key, [0]))
        
        if next_state_key not in self.q_table:
            self.q_table[next_state_key] = [0.0] * len(self.q_table[state_key])
        
        current_q = self.q_table[state_key][action]
        max_next_q = max(self.q_table[next_state_key])
        
        # Tính gradient
        gradient = reward + self.discount_factor * max_next_q - current_q
        
        # Cập nhật Q-value với AdamW
        params = {f"{state_key}_{action}": current_q}
        grads = {f"{state_key}_{action}": gradient}
        updated_params = self.optimizer.update(params, grads)
        
        new_q = updated_params[f"{state_key}_{action}"]
        self.q_table[state_key][action] = new_q
    
    def train(self, episodes, initial_cpu=50, initial_memory=50, initial_queue=5, max_queue=20):
        """
        Huấn luyện agent qua nhiều episodes với môi trường dynamic workload
        """
        training_log = []
        
        for episode in range(episodes):
            episode_reward = 0
            episode_step = 0
            
            # Khởi tạo trạng thái hệ thống
            cpu_util = initial_cpu
            memory_usage = initial_memory
            queue_length = initial_queue
            
            max_steps = 100  # Giới hạn số bước mỗi episode
            
            for step in range(max_steps):
                state_key = self.get_state_key(cpu_util, memory_usage, queue_length)
                
                # Chọn action (4 actions: giảm ưu tiên, giữ nguyên, tăng ưu tiên, cấp phát thêm)
                action = self.get_action(state_key, 4)
                
                # Mô phỏng tác động của action lên hệ thống
                if action == 0:  # Giảm độ ưu tiên
                    cpu_util = max(0, cpu_util - random.uniform(5, 15))
                    memory_usage = max(0, memory_usage - random.uniform(2, 8))
                    queue_length = min(max_queue, queue_length + random.randint(0, 2))
                elif action == 1:  # Giữ nguyên
                    cpu_util = max(0, min(100, cpu_util + random.uniform(-5, 5)))
                    memory_usage = max(0, min(100, memory_usage + random.uniform(-3, 3)))
                    queue_length = min(max_queue, max(0, queue_length + random.randint(-1, 1)))
                elif action == 2:  # Tăng độ ưu tiên
                    cpu_util = min(100, cpu_util + random.uniform(10, 20))
                    memory_usage = min(100, memory_usage + random.uniform(5, 10))
                    queue_length = max(0, queue_length - random.randint(1, 3))
                elif action == 3:  # Cấp phát thêm tài nguyên
                    cpu_util = max(0, cpu_util - random.uniform(15, 25))
                    memory_usage = max(0, memory_usage - random.uniform(10, 15))
                    queue_length = max(0, queue_length - random.randint(2, 4))
                
                # Tính reward
                reward = self.calculate_reward(cpu_util, memory_usage, queue_length)
                episode_reward += reward
                
                # Lưu vào experience replay
                next_state_key = self.get_state_key(cpu_util, memory_usage, queue_length)
                self.replay_buffer.push(state_key, action, reward, next_state_key)
                
                # Cập nhật Q-value
                self.update_q_value(state_key, action, reward, next_state_key)
                
                # Experience Replay: huấn luyện lại từ buffer
                if len(self.replay_buffer) > 32:
                    batch = self.replay_buffer.sample(32)
                    for s, a, r, ns in batch:
                        self.update_q_value(s, a, r, ns)
                
                episode_step += 1
            
            # Giảm epsilon theo thời gian (exploration decay)
            self.epsilon = max(0.01, self.epsilon * 0.995)
            
            self.episode_rewards.append(episode_reward)
            self.episode_steps.append(episode_step)
            
            training_log.append({
                'episode': episode + 1,
                'reward': episode_reward,
                'steps': episode_step,
                'epsilon': self.epsilon,
                'final_cpu': cpu_util,
                'final_memory': memory_usage,
                'final_queue': queue_length,
            })
        
        return {
            'training_log': training_log,
            'episode_rewards': self.episode_rewards,
            'episode_steps': self.episode_steps,
            'final_epsilon': self.epsilon,
            'q_table_size': len(self.q_table),
        }


def aqsa_schedule(episodes=100, initial_cpu=50, initial_memory=50, initial_queue=5):
    """
    Sử dụng AQSA để quản lý khối lượng công việc thích ứng và lập lịch tài nguyên
    
    Args:
        episodes: int - số episodes để huấn luyện
        initial_cpu: float - CPU utilization ban đầu (%)
        initial_memory: float - Memory usage ban đầu (%)
        initial_queue: int - Độ dài hàng đợi ban đầu
    
    Returns:
        dict:
            training_log: list[dict] - log huấn luyện
            episode_rewards: list[float] - reward qua các episodes
            q_table_size: int - kích thước Q-table
            final_epsilon: float - epsilon cuối cùng
    """
    # Tạo và huấn luyện agent AQSA
    agent = AQSAgent(learning_rate=0.0001, discount_factor=0.99, epsilon=0.1, weight_decay=0.01)
    training_result = agent.train(episodes, initial_cpu, initial_memory, initial_queue)
    
    return {
        'training_log': training_result['training_log'],
        'episode_rewards': training_result['episode_rewards'],
        'episode_steps': training_result['episode_steps'],
        'q_table_size': training_result['q_table_size'],
        'final_epsilon': training_result['final_epsilon'],
    }

