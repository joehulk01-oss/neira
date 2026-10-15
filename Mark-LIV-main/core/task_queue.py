"""
TASK QUEUE — antrean tugas async berprioritas untuk Neira.

Adopsi pola terbaik Brahma-Echo (agent/task_queue.py) supaya UI tidak pernah
nge-hang: tugas berat (agent, riset, render, unduhan) dijalankan di thread
terpisah, bisa dibatalkan lewat `cancel_flag`, dan hasilnya dikirim balik lewat
callback `on_complete`.

Pemakaian:
    from core.task_queue import get_queue, TaskPriority

    q = get_queue()
    tid = q.submit(lambda cancel: berat(...), priority=TaskPriority.HIGH,
                   on_complete=lambda task_id, result: ...)
    q.cancel(tid)          # batalkan kapan saja
    q.get_status(tid)      # {"status": "pending|running|completed|failed|cancelled", ...}

Kontrak fungsi tugas: `fn(cancel_flag: threading.Event) -> Any`. Fungsi boleh
mengabaikan `cancel_flag`, tapi sebaiknya mengecek `cancel_flag.is_set()` di
titik-titik panjang supaya pembatalan cepat.
"""
from __future__ import annotations

import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

for _stream in ("stdout", "stderr"):
    try:
        _s = getattr(sys, _stream, None)
        if _s is not None and hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(Enum):
    LOW = 3
    NORMAL = 2
    HIGH = 1


@dataclass(order=True)
class Task:
    priority: int
    created_at: float = field(compare=False)
    task_id: str = field(compare=False)
    label: str = field(compare=False, default="")
    status: TaskStatus = field(compare=False, default=TaskStatus.PENDING)
    result: Any = field(compare=False, default=None)
    error: str = field(compare=False, default="")
    fn: Any = field(compare=False, default=None)
    on_complete: Any = field(compare=False, default=None)
    cancel_flag: threading.Event = field(compare=False, default_factory=threading.Event)


class TaskQueue:
    """Worker thread + priority queue + pembatalan aman."""

    def __init__(self, max_concurrent: int = 1) -> None:
        self._queue: List[Task] = []
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._tasks: Dict[str, Task] = {}
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._max_concurrent = max_concurrent
        self._active_count = 0

    # ---- lifecycle -------------------------------------------------------- #
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop, daemon=True, name="NeiraTaskQueue"
        )
        self._worker_thread.start()
        print("[TaskQueue] ✅ Antrean tugas aktif")

    def stop(self) -> None:
        self._running = False
        with self._condition:
            self._condition.notify_all()
        print("[TaskQueue] 🔴 Antrean tugas berhenti")

    # ---- operasi ---------------------------------------------------------- #
    def submit(
        self,
        fn: Callable[[threading.Event], Any],
        label: str = "",
        priority: TaskPriority = TaskPriority.NORMAL,
        on_complete: Optional[Callable[[str, Any], None]] = None,
    ) -> str:
        """Masukkan tugas; langsung balik `task_id` (non-blocking)."""
        task_id = uuid.uuid4().hex[:8]
        task = Task(
            priority=priority.value,
            created_at=time.time(),
            task_id=task_id,
            label=label or getattr(fn, "__name__", "tugas"),
            fn=fn,
            on_complete=on_complete,
        )
        with self._condition:
            self._queue.append(task)
            self._queue.sort(key=lambda t: (t.priority, t.created_at))
            self._tasks[task_id] = task
            self._condition.notify()
        print(f"[TaskQueue] 📥 Antre: [{task_id}] {task.label[:60]}")
        return task_id

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                return False
            task.cancel_flag.set()
            task.status = TaskStatus.CANCELLED
            print(f"[TaskQueue] 🚫 Dibatalkan: [{task_id}]")
            return True

    def get_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            return {
                "task_id": task.task_id,
                "label": task.label,
                "status": task.status.value,
                "result": task.result,
                "error": task.error,
            }

    def get_all_statuses(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {"task_id": t.task_id, "label": t.label[:50], "status": t.status.value}
                for t in self._tasks.values()
            ]

    def pending_count(self) -> int:
        with self._lock:
            return sum(1 for t in self._queue if t.status == TaskStatus.PENDING)

    # ---- worker ----------------------------------------------------------- #
    def _worker_loop(self) -> None:
        while self._running:
            task = None
            with self._condition:
                while self._running and not self._next_task():
                    self._condition.wait(timeout=1.0)
                task = self._next_task()
                if task:
                    task.status = TaskStatus.RUNNING
                    self._active_count += 1
                    try:
                        self._queue.remove(task)
                    except ValueError:
                        pass
            if task:
                threading.Thread(
                    target=self._run_task, args=(task,),
                    daemon=True, name=f"NeiraTask-{task.task_id}",
                ).start()

    def _next_task(self) -> Optional[Task]:
        if self._active_count >= self._max_concurrent:
            return None
        for task in self._queue:
            if task.status == TaskStatus.PENDING and not task.cancel_flag.is_set():
                return task
        return None

    def _run_task(self, task: Task) -> None:
        print(f"[TaskQueue] ▶️ Jalankan: [{task.task_id}] {task.label[:60]}")
        try:
            result = task.fn(task.cancel_flag)
            with self._lock:
                if task.cancel_flag.is_set():
                    task.status = TaskStatus.CANCELLED
                else:
                    task.status = TaskStatus.COMPLETED
                    task.result = result
                self._active_count -= 1
            if task.on_complete and not task.cancel_flag.is_set():
                try:
                    task.on_complete(task.task_id, result)
                except Exception as e:
                    print(f"[TaskQueue] ⚠️ galat callback on_complete: {e}")
            print(f"[TaskQueue] ✅ Selesai: [{task.task_id}]")
        except Exception as e:
            with self._lock:
                task.status = TaskStatus.FAILED
                task.error = str(e)
                self._active_count -= 1
            print(f"[TaskQueue] ❌ Gagal: [{task.task_id}] {e}")
        with self._condition:
            self._condition.notify()


_queue: Optional[TaskQueue] = None
_queue_lock = threading.Lock()


def get_queue() -> TaskQueue:
    """Singleton antrean tugas (auto-start saat pertama dipakai)."""
    global _queue
    with _queue_lock:
        if _queue is None:
            _queue = TaskQueue()
            _queue.start()
    return _queue
