"""
Chạy và đóng gói kết quả mọi thuật toán lập lịch cho trang so sánh.
"""

import time as time_module

from .scheduling_algorithms import (
    fcfs, sjf, round_robin, calc_stats, count_context_switches,
)
from .omdrrs_scheduler import schedule_omdrrs
from .q_learning_scheduler import schedule_q_learning


def _timeline_payload(timeline):
    return [
        {
            'pid': seg['pid'],
            'name': seg.get('name', f"P{seg['pid']}"),
            'start': seg['start'],
            'end': seg['end'],
            'wait': seg.get('wait', 0),
            'tat': seg.get('tat', 0),
            'response': seg.get('response', seg.get('wait', 0)),
        }
        for seg in timeline
    ]


def _events_from_timeline(timeline, label_prefix=''):
    events = []
    for i, seg in enumerate(timeline, start=1):
        events.append({
            'step': i,
            'pid': seg['pid'],
            'name': seg.get('name', f"P{seg['pid']}"),
            'start': seg['start'],
            'end': seg['end'],
            'duration': max(0, seg['end'] - seg['start']),
            'message': f"{label_prefix}{seg.get('name', '')} chạy {seg['start']}→{seg['end']}",
        })
    return events


def _package_result(key, name, timeline, processes, compute_ms, extra=None):
    stats = calc_stats(timeline, processes)
    stats['context_switches'] = count_context_switches(timeline)
    stats['makespan'] = max((s['end'] for s in timeline), default=0)
    row = {
        'key': key,
        'name': name,
        'timeline': _timeline_payload(timeline),
        'events': _events_from_timeline(timeline),
        'stats': stats,
        'compute_ms': round(compute_ms, 2),
        'segment_count': len(timeline),
    }
    if extra:
        row.update(extra)
    return row


def run_all_schedulers(processes, quantum=20, q_episodes=100, seed=None):
    """Chay FCFS, SJF, RR, OMDRRS va Q-Learning tren cung bo tien trinh."""
    if not processes:
        return []

    results = []

    t0 = time_module.perf_counter()
    tl = fcfs(processes)
    results.append(_package_result('fcfs', 'FCFS', tl, processes, (time_module.perf_counter() - t0) * 1000))

    t0 = time_module.perf_counter()
    tl = sjf(processes)
    results.append(_package_result('sjf', 'SJF', tl, processes, (time_module.perf_counter() - t0) * 1000))

    t0 = time_module.perf_counter()
    tl = round_robin(processes, quantum)
    results.append(_package_result(
        'rr', f'Round Robin (q={quantum})', tl, processes,
        (time_module.perf_counter() - t0) * 1000,
        {'quantum': quantum},
    ))

    t0 = time_module.perf_counter()
    tl = schedule_omdrrs(processes)
    results.append(_package_result('omdrrs', 'OMDRRS', tl, processes, (time_module.perf_counter() - t0) * 1000))

    ql = schedule_q_learning(processes, episodes=q_episodes, seed=seed, quantum=max(4, quantum // 3))
    results.append(_package_result(
        'qlearning',
        'Q-Learning',
        ql['timeline'],
        processes,
        ql['train_ms'] + ql['schedule_ms'],
        {
            'train_ms': ql['train_ms'],
            'schedule_ms': ql['schedule_ms'],
            'episodes': ql['episodes'],
            'q_table_size': ql['q_table_size'],
            'steps': ql['steps'],
            'context_switches_ql': ql['context_switches'],
        },
    ))
    results[-1]['stats']['context_switches'] = ql['context_switches']

    return results
