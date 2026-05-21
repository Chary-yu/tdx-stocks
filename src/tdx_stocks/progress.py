from __future__ import annotations

import sys
from collections.abc import Callable
from time import perf_counter

from .console import print_notice

ProgressCallback = Callable[[str], None]


class RunProgress:
    def __init__(self, task_type: str, *, stream=None) -> None:
        self.task_type = task_type
        self.stream = sys.stderr if stream is None else stream
        self.started_at = perf_counter()
        self.count = 0

    def start(self) -> None:
        print_notice(f"运行进度：开始执行 {self.task_type}。", stream=self.stream)

    def __call__(self, message: str) -> None:
        self.count += 1
        print_notice(f"运行进度 [{self.count}]：{message}", stream=self.stream)

    def finish(self, status: str) -> None:
        elapsed = perf_counter() - self.started_at
        print_notice(f"运行进度：{self.task_type} 已结束，状态：{_status_label(status)}，耗时 {elapsed:.1f} 秒。", stream=self.stream)


def emit_progress(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _status_label(status: object) -> str:
    if status == "success":
        return "成功"
    if status == "failed":
        return "失败"
    if status == "skipped":
        return "已跳过"
    return str(status)
