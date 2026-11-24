"""Worker processes: tasks handed out, each answer handed back as it finishes, and a count from inside each task.

Nothing here measures or runs physics. A running task says how far it is through a meter, in whichever process runs
it, so a caller can see a stuck worker as a count that stops rising. A caller that stops early does not wait: tasks
not yet started are dropped and the worker processes are ended.
"""
import functools
import multiprocessing
import os
import pickle
import queue
import tempfile
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path

EVERY_S = 0.5       # how often at most a running task says how far it is
POLL_S = 0.2        # how often the counts from worker processes are read while no answer comes

_worker = None      # in a worker process: (the function that answers a task, where counts are sent, how often at most)


def default_workers():
    """Half the machine's cores, at least one. The caller may always choose another count."""
    return max(1, (os.cpu_count() or 2) // 2)


class Meter:
    """How far one task is: called with (done, of) as often as the task likes, and passed on now and then."""

    def __init__(self, tell, every_s):
        self.tell, self.every_s, self.next, self.last = tell, every_s, 0.0, None

    def __call__(self, done, of):
        self.last = (done, of)
        now = time.perf_counter()
        if now >= self.next:
            self.next = now + self.every_s
            self.tell(done, of)


def silent(*_):
    """What listens when nobody does."""


def _begin(start, told, every_s):
    global _worker
    told.cancel_join_thread()       # a worker that is ended never waits for its counts to be read
    begin, arguments = pickle.loads(Path(start).read_bytes())
    _worker = (begin(*arguments), told, every_s)


def _work(number, task):
    """(this process, the last count, the answer) of one task, in a worker process."""
    answer, told, every_s = _worker
    process = os.getpid()
    meter = Meter(lambda done, of: told.put((number, process, done, of)), every_s)
    found = answer(task, meter)
    return process, meter.last, found


class Crew:
    """Answers tasks in this process, or in worker processes that stay for the next asking.

    begin(*arguments) is called once in each process that works and returns answer(task, meter); both must be plain
    module-level functions, and the arguments plain data, so they can be sent to a worker. here, when given, is the
    answer function to use in this process.
    """

    def __init__(self, begin, arguments=(), workers=None, every_s=EVERY_S, here=None):
        self.begin, self.arguments, self.here, self.every_s = begin, arguments, here, every_s
        self.workers = default_workers() if workers is None else max(1, int(workers))
        self.pool, self.told, self.folder, self.given = None, None, None, 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        if self.pool is not None:
            self.pool.shutdown()
            self.folder.cleanup()
            self.pool = None

    def ask(self, tasks, notice=silent):
        """Yield (task index, process, answer) for each task as it finishes: in order in this process, else as the workers
        finish them. notice(task index, process, done, of) hears the counts, and each task's last one before its answer.

        Closing this generator, or an error in it, ends the worker processes and whatever they were doing.
        """
        if self.workers == 1 or len(tasks) <= 1:
            return self._in_this_process(tasks, notice)
        return self._shared(tasks, notice)

    def _in_this_process(self, tasks, notice):
        for index, task in enumerate(tasks):
            self.here = self.here or self.begin(*self.arguments)
            meter = Meter(functools.partial(notice, index, os.getpid()), self.every_s)
            answer = self.here(task, meter)
            if meter.last:
                notice(index, os.getpid(), *meter.last)
            yield index, os.getpid(), answer

    def _shared(self, tasks, notice):
        if self.pool is None:
            self._start()
        first, waiting = self.given, {}
        self.given += len(tasks)
        try:
            waiting = {self.pool.submit(_work, first + index, task): index for index, task in enumerate(tasks)}
            while waiting:
                done, _ = wait(waiting, timeout=POLL_S, return_when=FIRST_COMPLETED)
                self._hear(notice, first, set(waiting.values()))
                for future in sorted(done, key=waiting.get):
                    index = waiting.pop(future)
                    process, last, answer = future.result()
                    if last:
                        notice(index, process, *last)
                    yield index, process, answer
        finally:
            if waiting:
                self._end()

    def _start(self):
        """Make the pool. What each worker starts with waits for it in a temporary file, because arguments too big for a pipe
        handed to a process that dies as it starts would leave this one waiting for good."""
        self.folder, self.told = tempfile.TemporaryDirectory(ignore_cleanup_errors=True), multiprocessing.Queue()
        start = Path(self.folder.name) / "start"
        start.write_bytes(pickle.dumps((self.begin, self.arguments)))
        self.pool = ProcessPoolExecutor(self.workers, initializer=_begin, initargs=(str(start), self.told, self.every_s))

    def _hear(self, notice, first, running):
        """Pass on every count that has arrived from a task still running."""
        while True:
            try:
                number, process, done, of = self.told.get_nowait()
            except queue.Empty:
                return
            if number - first in running:
                notice(number - first, process, done, of)

    def _end(self):
        """End the worker processes now, whatever they are doing."""
        pool, self.pool = self.pool, None
        processes = list((pool._processes or {}).values())      # before Python 3.14 there is no public way to end a running worker
        pool.shutdown(wait=False, cancel_futures=True)
        for process in processes:
            process.terminate()
        self.folder.cleanup()
