"""
Q-Learning cho lập lịch CPU (theo bài: Reinforcement Learning for Adaptive
Resource Scheduling in Complex System Environments — docs/Q_learning.pdf).

- State: CPU utilization, memory load (proxy), queue length (rời rạc hóa).
- Action: chọn tiến trình trong Ready Queue.
- Reward: r_t = -(CPU + Memory + QueueLength) + thưởng hoàn thành.
- Cập nhật Q: Q(s,a) ← Q(s,a) + α[r + γ max Q(s',a') − Q(s,a)]; ε-greedy.
"""

import random
import time as time_module


class QLearningCPUScheduler:
    def __init__(self, alpha=0.18, gamma=0.9, epsilon=0.3, seed=None):
        self.alpha = alpha
        self.gamma = gamma
        self.epsilon = epsilon
        self.rng = random.Random(seed)
        self.q = {}

    def _bucket(self, value, edges):
        for i, edge in enumerate(edges):
            if value <= edge:
                return i
        return len(edges)

    def state_key(self, clock, ready, pending_count):
        if not ready:
            return ('idle', pending_count, self._bucket(clock, [12, 35, 70, 120]))
        rems = [p['remaining'] for p in ready]
        prios = [p.get('priority', 3) for p in ready]
        return (
            len(ready),
            pending_count,
            self._bucket(min(rems), [4, 10, 20, 40]),
            self._bucket(sum(rems) / len(rems), [8, 20, 45]),
            self._bucket(min(prios), [2, 4, 6]),
            self._bucket(clock, [15, 40, 90]),
        )

    def q_value(self, state, action):
        return self.q.get((state, action), 0.0)

    def choose_action(self, state, n_actions, greedy=False):
        if n_actions <= 0:
            return 0
        if not greedy and self.rng.random() < self.epsilon:
            return self.rng.randrange(n_actions)
        best_q = max(self.q_value(state, a) for a in range(n_actions))
        candidates = [a for a in range(n_actions) if self.q_value(state, a) == best_q]
        return self.rng.choice(candidates)

    def update(self, state, action, reward, next_state, n_next_actions, done):
        old = self.q_value(state, action)
        if done or n_next_actions == 0:
            target = reward
        else:
            next_max = max(self.q_value(next_state, a) for a in range(n_next_actions))
            target = reward + self.gamma * next_max
        self.q[(state, action)] = old + self.alpha * (target - old)

    def _normalize_processes(self, processes):
        rows = []
        for i, p in enumerate(processes):
            burst = max(1, int(p.get('burst', 1)))
            arrival = max(0, int(p.get('arrival', 0)))
            priority = max(1, min(9, int(p.get('priority', 3))))
            rows.append({
                'pid': p.get('pid', i + 1),
                'name': p.get('name', f"P{i + 1}"),
                'arrival': arrival,
                'burst': burst,
                'priority': priority,
                'remaining': burst,
            })
        return rows

    def _time_slice(self, proc, ready_len):
        base = max(2, min(12, proc['remaining']))
        if ready_len > 3:
            base = max(2, base // 2)
        if proc.get('priority', 3) <= 2:
            base += 2
        return min(proc['remaining'], base)

    def _system_metrics(self, ready, pending, slice_time, total_burst):
        """Ánh xạ state trong PDF: CPU, Memory, QueueLength."""
        queue_len = len(ready) + len(pending)
        memory_load = sum(p['remaining'] for p in ready) + sum(p['burst'] for p in pending)
        total_cap = max(1, total_burst)
        cpu_util = min(100.0, (slice_time / max(1, len(ready))) * 25.0)
        return cpu_util, (memory_load / total_cap) * 50.0, float(queue_len)

    def _step_reward(self, ready, pending, slice_time, total_burst, completed):
        cpu_u, mem_u, q_len = self._system_metrics(ready, pending, slice_time, total_burst)
        reward = -(cpu_u + mem_u + q_len)
        if completed:
            reward += 20.0
        return reward

    def train_episode(self, processes, quantum_hint=6):
        internal = self._normalize_processes(processes)
        total_burst = sum(p['burst'] for p in internal) or 1
        pending = sorted(internal, key=lambda x: (x['arrival'], x['pid']))
        ready = []
        clock = 0
        last_pid = None

        def pull():
            nonlocal pending, clock
            while pending and pending[0]['arrival'] <= clock:
                ready.append(pending.pop(0))
            ready.sort(key=lambda x: x['pid'])

        pull()
        while pending or ready:
            if not ready:
                clock = pending[0]['arrival']
                pull()
                continue

            state = self.state_key(clock, ready, len(pending))
            action = self.choose_action(state, len(ready), greedy=False)
            action = min(action, len(ready) - 1)
            selected = ready[action]
            switched = last_pid is not None and last_pid != selected['pid']
            slice_t = min(self._time_slice(selected, len(ready)), quantum_hint)
            slice_t = min(slice_t, selected['remaining'])

            start = clock
            clock += slice_t
            selected['remaining'] -= slice_t
            pull()

            completed = selected['remaining'] == 0
            if completed:
                ready = [p for p in ready if p['pid'] != selected['pid']]
            else:
                ready = [p for i, p in enumerate(ready) if i != action]
                ready.append(selected)
                ready.sort(key=lambda x: x['pid'])

            reward = self._step_reward(ready, pending, slice_t, total_burst, completed)
            next_state = self.state_key(clock, ready, len(pending))
            n_next = len(ready)
            done = not pending and not ready
            self.update(state, action, reward, next_state, n_next, done)
            last_pid = selected['pid']

    def simulate(self, processes, greedy=True, quantum_hint=6):
        """Chạy lịch với policy đã học; trả về timeline + steps cho animation."""
        internal = self._normalize_processes(processes)
        pending = sorted(internal, key=lambda x: (x['arrival'], x['pid']))
        ready = []
        clock = 0
        timeline = []
        steps = []
        first_start = {}
        last_pid = None
        context_switches = 0

        def pull():
            nonlocal pending, clock
            while pending and pending[0]['arrival'] <= clock:
                ready.append(pending.pop(0))
            ready.sort(key=lambda x: x['pid'])

        pull()
        while pending or ready:
            if not ready:
                clock = pending[0]['arrival']
                pull()
                continue

            state = self.state_key(clock, ready, len(pending))
            action = self.choose_action(state, len(ready), greedy=greedy)
            action = min(action, len(ready) - 1)
            selected = ready[action]
            if last_pid is not None and last_pid != selected['pid']:
                context_switches += 1

            slice_t = min(self._time_slice(selected, len(ready)), quantum_hint)
            slice_t = min(slice_t, selected['remaining'])
            start = clock
            end = clock + slice_t

            if selected['pid'] not in first_start:
                first_start[selected['pid']] = start

            q_pick = self.q_value(state, action)
            steps.append({
                'pid': selected['pid'],
                'name': selected['name'],
                'start': start,
                'end': end,
                'slice': slice_t,
                'q_value': round(q_pick, 3),
                'state': str(state),
                'action': action,
                'explanation': (
                    f"Q-Learning chọn {selected['name']} (action={action}, Q={q_pick:.2f}) "
                    f"tại trạng thái ready={len(ready)}, pending={len(pending)}. "
                    f"Cấp CPU {slice_t} đơn vị thời gian."
                ),
            })

            selected['remaining'] -= slice_t
            clock = end
            pull()

            if selected['remaining'] == 0:
                ready = [p for p in ready if p['pid'] != selected['pid']]
            else:
                ready = [p for i, p in enumerate(ready) if i != action]
                ready.append(selected)
                ready.sort(key=lambda x: x['pid'])

            orig = next(x for x in internal if x['pid'] == selected['pid'])
            timeline.append({
                **orig,
                'start': start,
                'end': end,
                'wait': first_start[selected['pid']] - orig['arrival'],
                'response': first_start[selected['pid']] - orig['arrival'],
                'tat': 0,
            })
            last_pid = selected['pid']

        last_end = {}
        for seg in timeline:
            last_end[seg['pid']] = seg['end']
        for seg in timeline:
            orig = next(x for x in internal if x['pid'] == seg['pid'])
            seg['tat'] = last_end[seg['pid']] - orig['arrival']

        return timeline, steps, context_switches


def schedule_q_learning(processes, episodes=100, seed=None, quantum=6):
    """
    Huấn luyện nhanh rồi lập lịch — trả về dict cho trang so sánh.
    """
    t0 = time_module.perf_counter()
    agent = QLearningCPUScheduler(seed=seed)
    base = agent._normalize_processes(processes)
    if not base:
        return {
            'timeline': [],
            'steps': [],
            'context_switches': 0,
            'train_ms': 0,
            'schedule_ms': 0,
            'episodes': 0,
            'q_table_size': 0,
        }

    for ep in range(episodes):
        mutated = []
        for p in base:
            jitter = agent.rng.randint(-1, 1) if ep > 0 else 0
            mutated.append({
                **p,
                'arrival': max(0, p['arrival'] + jitter),
                'burst': max(1, p['burst'] + (1 if ep % 3 == 0 else 0)),
            })
        agent.train_episode(mutated, quantum_hint=quantum)

    train_ms = (time_module.perf_counter() - t0) * 1000
    t1 = time_module.perf_counter()
    timeline, steps, context_switches = agent.simulate(base, greedy=True, quantum_hint=quantum)
    schedule_ms = (time_module.perf_counter() - t1) * 1000

    return {
        'timeline': timeline,
        'steps': steps,
        'context_switches': context_switches,
        'train_ms': round(train_ms, 2),
        'schedule_ms': round(schedule_ms, 2),
        'episodes': episodes,
        'q_table_size': len(agent.q),
    }
