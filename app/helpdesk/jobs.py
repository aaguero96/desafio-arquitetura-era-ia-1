"""Tarefas em segundo plano, com estado em memória (ADR 0010).

Estado se perde num reinício da aplicação: aceitável, está fora do escopo.
"""
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from threading import Lock

from pydantic import BaseModel

from .schemas import JobStatus

Progress = Callable[[int, int], None]


@dataclass
class _Job:
    status: JobStatus = field(default_factory=lambda: JobStatus(state="pending"))
    result: BaseModel | None = None


class Jobs:
    def __init__(self, workers: int):
        self._pool = ThreadPoolExecutor(workers)
        self._jobs: dict[str, _Job] = {}
        self._lock = Lock()

    def submit(self, work: Callable[[Progress], BaseModel]) -> str:
        job_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._jobs[job_id] = _Job()
        self._pool.submit(self._run, job_id, work)
        return job_id

    def status(self, job_id: str) -> JobStatus | None:
        job = self._jobs.get(job_id)
        return job.status if job else None

    def result(self, job_id: str) -> BaseModel | None:
        job = self._jobs.get(job_id)
        return job.result if job else None

    def _run(self, job_id: str, work: Callable[[Progress], BaseModel]) -> None:
        job = self._jobs[job_id]

        def progress(done: int, total: int) -> None:
            job.status = JobStatus(state="running", progress=f"{done}/{total}")

        job.status = JobStatus(state="running")
        try:
            job.result = work(progress)
        except Exception as error:  # qualquer falha vira `failed` com motivo; nunca fica em `running`
            job.status = JobStatus(state="failed", progress=job.status.progress,
                                   reason=str(error) or type(error).__name__)
            return
        job.status = JobStatus(state="done", progress=job.status.progress)
