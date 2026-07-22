import random
from itertools import cycle


def parse_reference_string(raw_text, fallback=None, limit=None):
    """Parse a comma/space separated page reference string into integers."""
    values = []
    raw_text = (raw_text or "").replace(";", ",")
    for token in raw_text.replace("\n", ",").split(","):
        token = token.strip()
        if not token:
            continue
        try:
            values.append(int(token))
        except ValueError:
            continue

    if not values and fallback:
        values = list(fallback)
    if limit is not None:
        values = values[:limit]
    return values


def build_memory_reference_stream(mode, sessions=None, queue_items=None, length=18, seed=""):
    """Build a deterministic reference stream for the memory simulation."""
    sessions = list(sessions or [])
    queue_items = list(queue_items or [])

    if mode == "manual":
        return []

    if mode == "random":
        rng = random.Random(seed) if seed else random.Random()
        return [rng.randint(1, 9) for _ in range(max(6, length))]

    refs = []
    for sess in sessions:
        machine_id = getattr(sess.machine, "id", 0) or 0
        refs.extend([
            (getattr(sess, "id", 0) % 9) + 1,
            (machine_id % 9) + 1,
            max(1, min(9, (getattr(sess, "planned_minutes", 60) // 15) or 1)),
        ])

    for item in queue_items:
        refs.extend([
            (len(getattr(item, "customer_name", "")) % 9) + 1,
            max(1, min(9, getattr(item, "planned_minutes", 60) // 10 or 1)),
        ])

    if not refs:
        return []

    if len(refs) < length:
        base = list(refs)
        while len(refs) < length:
            refs.extend(base)

    return refs[:length]


def _memory_stats(steps, refs):
    faults = sum(1 for step in steps if not step["hit"])
    total = len(refs) or 1
    hits = total - faults
    fault_rate = round(faults / total * 100, 1)
    hit_rate = round(hits / total * 100, 1)
    return {
        "references": len(refs),
        "faults": faults,
        "hits": hits,
        "fault_rate": fault_rate,
        "hit_rate": hit_rate,
    }


def simulate_fifo(refs, frame_count=3):
    frames = [None] * frame_count
    queue = []
    steps = []

    for index, ref in enumerate(refs, start=1):
        hit = ref in frames
        replaced = None
        slot = None

        if hit:
            slot = frames.index(ref)
        else:
            if None in frames:
                slot = frames.index(None)
                frames[slot] = ref
                queue.append(slot)
            else:
                slot = queue.pop(0)
                replaced = frames[slot]
                frames[slot] = ref
                queue.append(slot)

        steps.append({
            "step": index,
            "ref": ref,
            "hit": hit,
            "replaced": replaced,
            "slot": slot,
            "frames": list(frames),
        })

    return {
        "name": "FIFO",
        "steps": steps,
        "stats": _memory_stats(steps, refs),
    }


def simulate_lru(refs, frame_count=3):
    frames = [None] * frame_count
    last_used = {}
    steps = []

    for index, ref in enumerate(refs, start=1):
        hit = ref in frames
        replaced = None
        slot = None

        if hit:
            slot = frames.index(ref)
        else:
            if None in frames:
                slot = frames.index(None)
                frames[slot] = ref
            else:
                lru_page = min((page for page in frames if page is not None), key=lambda page: last_used.get(page, -1))
                slot = frames.index(lru_page)
                replaced = frames[slot]
                frames[slot] = ref

        last_used[ref] = index
        steps.append({
            "step": index,
            "ref": ref,
            "hit": hit,
            "replaced": replaced,
            "slot": slot,
            "frames": list(frames),
        })

    return {
        "name": "LRU",
        "steps": steps,
        "stats": _memory_stats(steps, refs),
    }


def simulate_optimal(refs, frame_count=3):
    frames = [None] * frame_count
    steps = []

    for index, ref in enumerate(refs, start=1):
        hit = ref in frames
        replaced = None
        slot = None

        if hit:
            slot = frames.index(ref)
        else:
            if None in frames:
                slot = frames.index(None)
                frames[slot] = ref
            else:
                future = refs[index:]

                def next_use(page):
                    try:
                        return future.index(page)
                    except ValueError:
                        return float("inf")

                victim = max((page for page in frames if page is not None), key=next_use)
                slot = frames.index(victim)
                replaced = frames[slot]
                frames[slot] = ref

        steps.append({
            "step": index,
            "ref": ref,
            "hit": hit,
            "replaced": replaced,
            "slot": slot,
            "frames": list(frames),
        })

    return {
        "name": "OPT",
        "steps": steps,
        "stats": _memory_stats(steps, refs),
    }


def build_memory_comparison(refs, frame_count=3):
    """Return FIFO, LRU and OPT simulation results for comparison."""
    algorithms = [
        simulate_fifo(refs, frame_count),
        simulate_lru(refs, frame_count),
        simulate_optimal(refs, frame_count),
    ]
    best_faults = min(algorithms, key=lambda row: row["stats"]["faults"])["name"] if algorithms else ""
    best_hit = max(algorithms, key=lambda row: row["stats"]["hit_rate"])["name"] if algorithms else ""
    return {
        "algorithms": algorithms,
        "best_faults": best_faults,
        "best_hit": best_hit,
    }


def simulate_cpu_memory(timeline, total_ram=1024, mem_base=64, mem_per_minute=4, mem_cap=256):
    """Mô phỏng CPU cấp phát vùng nhớ cho tiến trình trong lúc nó đang được chạy.

    Hàm này KHÔNG phụ thuộc vào giải thuật lập lịch cụ thể — nó chỉ đọc lại
    `timeline` (kết quả trả về từ fcfs/sjf/round_robin/schedule_omdrrs, mỗi
    phần tử có ít nhất pid/name/start/end) rồi diễn giải thêm 1 lớp bộ nhớ:

        CPU chọn tiến trình chạy (đã có từ giải thuật)
          -> hệ điều hành CẤP một vùng RAM cho tiến trình trong lúc nó
             chiếm CPU (kích thước phụ thuộc độ dài lát cắt: mem_base +
             mem_per_minute * số phút chạy, tối đa mem_cap)
          -> khi tiến trình RỜI CPU (hết lát cắt / hoàn tất — context switch)
             thì vùng RAM đó được THU HỒI ngay lập tức.

    Vì vậy dùng được cho cả FCFS, SJF (non-preemptive, mỗi tiến trình 1 lát
    cắt trọn burst) và Round Robin / OMDRRS (preemptive, nhiều lát cắt).
    """
    ram_free = total_ram
    rows = []

    for seg in timeline:
        pid = seg.get('pid')
        name = seg.get('name') or f"P{pid}"
        start = seg.get('start', 0)
        end = seg.get('end', 0)
        duration = max(0, end - start)
        need_mem = min(mem_cap, mem_base + duration * mem_per_minute)

        finished = seg.get('remaining_after', 0) in (0, None) if 'remaining_after' in seg else True
        leave_reason = "hoàn tất công việc" if finished else "hết lượt CPU (context switch, còn dữ liệu chưa xử lý)"

        cpu_note = f"[CPU] {name} được lập lịch chạy từ phút {start} đến phút {end} ({duration} phút)."

        if ram_free < need_mem:
            allocated = False
            ram_used = 0
            mem_alloc_note = (
                f"[Bộ nhớ] {name} cần {need_mem}MB để nạp vào RAM nhưng hệ thống chỉ còn "
                f"{ram_free}MB trống → cấp phát trễ, tiến trình vẫn chiếm CPU nhưng phải chờ "
                f"tiến trình khác trả RAM trước khi nạp dữ liệu đầy đủ."
            )
            mem_return_note = ""
        else:
            allocated = True
            ram_free -= need_mem
            ram_used = need_mem
            mem_alloc_note = (
                f"[Bộ nhớ] Hệ điều hành cấp {need_mem}MB RAM cho {name} để nạp tiến trình vào bộ nhớ "
                f"trong lúc chiếm CPU (RAM trống còn {ram_free}MB)."
            )
            ram_free += ram_used
            mem_return_note = (
                f"[Bộ nhớ] {name} rời CPU vì {leave_reason}, hệ điều hành thu hồi {ram_used}MB RAM "
                f"vừa cấp (RAM trống hiện tại: {ram_free}MB)."
            )

        description = " ".join(part for part in [cpu_note, mem_alloc_note, mem_return_note] if part)

        rows.append({
            "pid": pid,
            "name": name,
            "start": start,
            "end": end,
            "duration": duration,
            "finished": finished,
            "need_mem": need_mem,
            "ram_used": ram_used,
            "ram_free": ram_free,
            "allocated": allocated,
            "description": description,
        })

    return {
        "rows": rows,
        "total_ram": total_ram,
        "ram_free": ram_free,
        "mem_base": mem_base,
        "mem_per_minute": mem_per_minute,
        "mem_cap": mem_cap,
    }


def simulate_bounded_buffer(buffer_size=3, sequence=None, producer_count=2, consumer_count=2,
                             total_ram=512, mem_producer=128, mem_consumer=96):
    """Simulate producer-consumer trên một vùng đệm hữu hạn, có mô phỏng thêm:

    1) Lập lịch CPU (FCFS): mỗi bước, CPU cấp lượt chạy cho đúng tiến trình
       đang ở vị trí kế tiếp trong `sequence` (mô phỏng hàng đợi FCFS).
    2) Cấp phát / thu hồi bộ nhớ: trước khi chạy, tiến trình phải xin hệ điều
       hành cấp một vùng RAM để làm việc (mem_producer/mem_consumer MB). Nếu
       RAM trống không đủ, tiến trình bị chặn ngay (chưa kịp vào vùng găng).
       Nếu đủ, RAM được cấp; và bất kể tiến trình có sản xuất/tiêu thụ thành
       công hay bị chặn ở bước đồng bộ, vùng RAM đó luôn được trả lại cho hệ
       thống ngay khi tiến trình chạy xong lượt của mình trong bước này.
    3) Đồng bộ hoá bằng semaphore + mutex đúng thứ tự kinh điển:
       wait(empty|full) -> wait(mutex) -> [vùng găng] -> signal(mutex)
       -> signal(full|empty).
    """
    sequence = list(sequence or [])

    buffer = []
    empty = buffer_size
    full = 0
    mutex = 1
    ram_free = total_ram
    producer_round = 0
    consumer_round = 0
    blocked_producers = 0
    blocked_consumers = 0
    blocked_by_memory = 0
    timeline = []

    for step, action in enumerate(sequence, start=1):
        before = list(buffer)
        item = None
        result = "blocked"
        block_reason = None
        ram_used = 0
        mem_return_note = ""

        if action == "P":
            producer_round += 1
            actor = f"Producer {((producer_round - 1) % max(1, producer_count)) + 1}"
            item = f"Job-{step}"
            need_mem = mem_producer
        else:
            consumer_round += 1
            actor = f"Consumer {((consumer_round - 1) % max(1, consumer_count)) + 1}"
            need_mem = mem_consumer

        sched_note = f"[Lập lịch-FCFS] Bước {step}: CPU cấp lượt chạy cho {actor} (đúng vị trí trong hàng đợi FCFS)."

        # --- Giai đoạn cấp phát bộ nhớ ---
        if ram_free < need_mem:
            block_reason = "memory"
            blocked_by_memory += 1
            mem_note = (
                f"[Bộ nhớ] {actor} xin cấp {need_mem}MB nhưng RAM trống chỉ còn {ram_free}MB "
                f"→ cấp phát thất bại, {actor} quay lại hàng đợi tiến trình, chưa được vào vùng găng."
            )
            mutex_note = "[Mutex] Không thực hiện wait(mutex) vì tiến trình bị chặn do thiếu bộ nhớ."
        else:
            ram_free -= need_mem
            ram_used = need_mem
            mem_alloc_note = f"[Bộ nhớ] Hệ điều hành cấp {need_mem}MB cho {actor} (RAM trống còn {ram_free}MB)."

            if action == "P":
                if empty > 0:
                    empty -= 1
                    mutex_note = f"[Mutex] {actor} wait(empty): empty→{empty}. "
                    mutex = 0
                    mutex_note += f"wait(mutex): mutex→0, {actor} vào vùng găng."
                    buffer.append(item)
                    full += 1
                    mutex_note += f" Ghi {item} vào buffer (buffer={list(buffer)})."
                    mutex = 1
                    mutex_note += f" signal(mutex): mutex→1, {actor} rời vùng găng. signal(full): full→{full}."
                    result = "produced"
                else:
                    block_reason = "buffer_full"
                    blocked_producers += 1
                    mutex_note = f"[Mutex] {actor} gọi wait(empty) nhưng empty=0 → bị chặn, không vào vùng găng."
            else:
                if full > 0:
                    full -= 1
                    mutex_note = f"[Mutex] {actor} wait(full): full→{full}. "
                    mutex = 0
                    mutex_note += f"wait(mutex): mutex→0, {actor} vào vùng găng."
                    item = buffer.pop(0)
                    empty += 1
                    mutex_note += f" Lấy {item} khỏi buffer (buffer={list(buffer)})."
                    mutex = 1
                    mutex_note += f" signal(mutex): mutex→1, {actor} rời vùng găng. signal(empty): empty→{empty}."
                    result = "consumed"
                else:
                    block_reason = "buffer_empty"
                    blocked_consumers += 1
                    mutex_note = f"[Mutex] {actor} gọi wait(full) nhưng full=0 → bị chặn, không vào vùng găng."

            # Chạy xong lượt (dù có sản xuất/tiêu thụ được hay không) -> trả RAM ngay
            ram_free += ram_used
            mem_return_note = (
                f"[Bộ nhớ] {actor} chạy xong lượt này, hệ điều hành thu hồi lại {ram_used}MB RAM đã cấp "
                f"(RAM trống hiện tại: {ram_free}MB)."
            )
            mem_note = mem_alloc_note

        if block_reason == "buffer_full":
            note = f"{actor} bị chặn vì buffer đầy."
        elif block_reason == "buffer_empty":
            note = f"{actor} bị chặn vì buffer rỗng."
        elif block_reason == "memory":
            note = f"{actor} bị chặn vì không đủ vùng nhớ trống."
        elif result == "produced":
            note = f"{actor} đưa {item} vào vùng đệm."
        else:
            note = f"{actor} lấy {item} ra khỏi vùng đệm."

        description = " ".join(part for part in [sched_note, mem_note, mutex_note, mem_return_note] if part)

        timeline.append({
            "step": step,
            "actor": actor,
            "action": action,
            "result": result,
            "block_reason": block_reason,
            "item": item,
            "note": note,
            "before": before,
            "buffer": list(buffer),
            "empty": empty,
            "full": full,
            "mutex": mutex,
            "need_mem": need_mem,
            "ram_used": ram_used,
            "ram_free": ram_free,
            "sched_note": sched_note,
            "mem_note": mem_note,
            "mutex_note": mutex_note,
            "description": description,
        })

    return {
        "timeline": timeline,
        "blocked_producers": blocked_producers,
        "blocked_consumers": blocked_consumers,
        "blocked_by_memory": blocked_by_memory,
        "final_buffer": list(buffer),
        "empty": empty,
        "full": full,
        "mutex": mutex,
        "total_ram": total_ram,
        "ram_free": ram_free,
        "mem_producer": mem_producer,
        "mem_consumer": mem_consumer,
    }
