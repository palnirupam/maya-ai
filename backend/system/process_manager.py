import logging
import asyncio
import subprocess
import os
import signal
from typing import Set

logger = logging.getLogger(__name__)

class ProcessManager:
    """
    Central registry for tracking PIDs and Asyncio Tasks spawned by Maya.
    Allows for Deep Emergency Stop (Process Tree Kill + Task Cancellation).
    """
    def __init__(self):
        self._tracked_pids: Set[int] = set()
        self._tracked_tasks: Set[asyncio.Task] = set()

    def register_pid(self, pid: int):
        self._tracked_pids.add(pid)
        logger.debug(f"ProcessManager: Registered PID {pid}")

    def unregister_pid(self, pid: int):
        self._tracked_pids.discard(pid)

    def register_task(self, task: asyncio.Task):
        self._tracked_tasks.add(task)
        # Automatically remove when done
        task.add_done_callback(self._tracked_tasks.discard)

    async def emergency_stop(self):
        """
        Executes the Graceful Stop Sequence:
        1. Cancel tracked asyncio tasks.
        2. Wait 2 seconds (Graceful shutdown window).
        3. Force kill tree for all tracked PIDs.
        """
        logger.warning("🚨 EMERGENCY STOP TRIGGERED 🚨")
        
        # 1. Cancel Tasks
        canceled_count = 0
        for task in list(self._tracked_tasks):
            if not task.done():
                task.cancel()
                canceled_count += 1
        logger.warning(f"Canceled {canceled_count} async tasks.")

        # 2. Graceful Wait
        await asyncio.sleep(2)

        # 3. Force Kill Tree
        killed_count = 0
        for pid in list(self._tracked_pids):
            try:
                # Windows Process Tree Kill
                if os.name == 'nt':
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
                else:
                    # POSIX: Kill process group
                    os.killpg(os.getpgid(pid), signal.SIGKILL)
                killed_count += 1
            except Exception as e:
                logger.error(f"Failed to kill PID {pid}: {e}")
            finally:
                self._tracked_pids.discard(pid)
                
        logger.warning(f"Force killed {killed_count} process trees.")
        return {"tasks_canceled": canceled_count, "pids_killed": killed_count}

process_manager = ProcessManager()
