"""
OMDRRS — Optimum Multilevel Dynamic Round Robin Scheduling (Python engine).
Dùng cho so sánh đa thuật toán phía server; dashboard chi tiết vẫn có thể dùng JS.
"""


def compute_f(burst, arrival, priority):
    return (burst * 0.2) + (arrival * 0.3) + (priority * 0.5)


def calc_dynamic_quantum(ready, selected):
    remaining = [p['remaining'] for p in ready]
    avg = sum(remaining) / len(remaining)
    min_rem = min(remaining)
    max_rem = max(remaining)
    priority_boost = max(0, 6 - selected.get('priority', 3)) * 1.15
    stability = min(4, (max_rem - min_rem) * 0.08) if len(ready) > 1 else 0
    return max(4, round((avg * 0.45) + (min_rem * 0.32) + (selected['remaining'] * 0.13) + priority_boost - stability))


def schedule_omdrrs(processes):
    """
    Trả về timeline (list segment) tương thích calc_stats / build_scheduling_events.
    Mỗi process cần: pid, name, arrival, burst; priority tùy chọn (mặc định 3).
    Bổ sung: f_values_snapshot, quantum_history, round_number, quantum_reason,
             avg_remaining_burst để hiển thị Decision Engine.
    """
    if not processes:
        return []

    internal = []
    for p in processes:
        burst = max(1, int(p.get('burst', 1)))
        arrival = max(0, int(p.get('arrival', 0)))
        priority = max(1, int(p.get('priority', 3)))
        internal.append({
            **p,
            'burst': burst,
            'arrival': arrival,
            'priority': priority,
            'remaining': burst,
            'f': compute_f(burst, arrival, priority),
        })

    pending = sorted(internal, key=lambda x: (x['arrival'], x['f'], x['priority'], x['pid']))
    ready = []
    timeline = []
    time = 0
    first_start = {}
    quantum_history = []   # [(round_number, quantum_value)]
    prev_quantum = None
    round_number = 0

    # Arrival events tổng
    arrival_events = sorted(
        [{'time': p['arrival'], 'name': p.get('name', f"P{p['pid']}"), 'pid': p['pid'],
          'customer_name': p.get('customer_name', p.get('name', f"KH{p['pid']}"))}
         for p in processes],
        key=lambda e: (e['time'], e['pid'])
    )

    def pull_arrivals(up_to):
        nonlocal pending
        while pending and pending[0]['arrival'] <= up_to:
            ready.append(pending.pop(0))

    pull_arrivals(time)

    while pending or ready:
        if not ready:
            time = pending[0]['arrival']
            pull_arrivals(time)
            continue

        ready.sort(key=lambda x: (x['f'], x['arrival'], x['priority'], x['pid']))
        selected = ready[0]
        ready_before = [q['pid'] for q in ready if q['pid'] != selected['pid']]
        ready_before_names = [q.get('name', f"P{q['pid']}") for q in ready if q['pid'] != selected['pid']]

        # Snapshot F-values của toàn bộ ready queue
        f_values_snapshot = sorted(
            [{'pid': q['pid'],
              'name': q.get('name', f"P{q['pid']}"),
              'f': round(q['f'], 2),
              'remaining': q['remaining'],
              'priority': q['priority'],
              'selected': q['pid'] == selected['pid']}
             for q in ready],
            key=lambda x: x['f']
        )

        # Tính avg remaining burst
        avg_remaining = round(sum(q['remaining'] for q in ready) / len(ready), 1) if ready else 0

        quantum = calc_dynamic_quantum(ready, selected)
        slice_time = min(selected['remaining'], quantum)
        start = time
        end = time + slice_time

        if selected['pid'] not in first_start:
            first_start[selected['pid']] = start

        # Quantum reason
        round_number += 1
        if prev_quantum is None:
            quantum_reason = f"Quantum khởi tạo = {quantum} phút dựa trên burst trung bình ({avg_remaining} phút)."
        elif quantum > prev_quantum:
            quantum_reason = f"Quantum tăng {prev_quantum} → {quantum} phút vì remaining burst trung bình tăng ({avg_remaining} phút)."
        elif quantum < prev_quantum:
            quantum_reason = f"Quantum giảm {prev_quantum} → {quantum} phút vì remaining burst trung bình giảm ({avg_remaining} phút)."
        else:
            quantum_reason = f"Quantum giữ nguyên = {quantum} phút (remaining burst ổn định ≈ {avg_remaining} phút)."

        quantum_history.append({'round': round_number, 'quantum': quantum})
        prev_quantum = quantum

        remaining_before = selected['remaining']
        selected['remaining'] -= slice_time
        time = end
        pull_arrivals(time)
        ready.pop(0)
        if selected['remaining'] > 0:
            ready.append(selected)

        queue_after = [q['pid'] for q in ready]
        queue_after_names = [q.get('name', f"P{q['pid']}") for q in ready]

        orig = next(x for x in internal if x['pid'] == selected['pid'])
        timeline.append({
            **orig,
            'start': start,
            'end': end,
            'wait': first_start[selected['pid']] - orig['arrival'],
            'response': first_start[selected['pid']] - orig['arrival'],
            'tat': 0,
            'ready_before': ready_before,
            'ready_before_names': ready_before_names,
            'queue_after': queue_after,
            'queue_after_names': queue_after_names,
            'remaining_before': remaining_before,
            'remaining_after': selected['remaining'],
            'quantum': quantum,
            'quantum_new': quantum,
            'quantum_reason': quantum_reason,
            'quantum_history': list(quantum_history),
            'round_number': round_number,
            'avg_remaining_burst': avg_remaining,
            'f_values': f_values_snapshot,
            'f_values_snapshot': f_values_snapshot,
            'arrival_events': arrival_events,
            'quantum_expired': selected['remaining'] > 0,
            'decision': (
                f"{selected['name']} được chọn vì F = {selected['f']:.1f} nhỏ nhất, "
                f"quantum động = {quantum}"
            ),
            'decision_reason': (
                f"{selected.get('name', 'P' + str(selected['pid']))} ???c ch?n v? "
                f"F-value = {selected['f']:.2f} nh? nh?t trong Ready Queue. "
                f"{quantum_reason}"
            ),
        })

    last_end = {}
    for seg in timeline:
        last_end[seg['pid']] = seg['end']
    for seg in timeline:
        orig = next(x for x in internal if x['pid'] == seg['pid'])
        seg['tat'] = last_end[seg['pid']] - orig['arrival']
        seg['wait'] = first_start[seg['pid']] - orig['arrival']

    return timeline
