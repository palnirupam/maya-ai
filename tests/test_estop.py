import asyncio
import time
from backend.system.process_manager import process_manager
from backend.tools.desktop.advanced.terminal_tools import execute_powershell

async def test_estop():
    print("Testing Deep Emergency Stop...")

    # Spawn a long running process in the background
    # We will use an asyncio task to run it because execute_powershell blocks
    def run_long_process():
        print("Starting a 30-second powershell sleep process...")
        # This will block the thread for 30s unless killed
        res = execute_powershell("Start-Sleep -Seconds 30; Write-Host 'Done sleeping'")
        print("Powershell Finished With:", res)

    # Run in background
    loop = asyncio.get_running_loop()
    task = loop.run_in_executor(None, run_long_process)

    # Let the process spawn
    await asyncio.sleep(2)

    # Trigger emergency stop
    print("\nTriggering Emergency Stop!")
    start = time.time()
    stats = await process_manager.emergency_stop()
    end = time.time()

    print(f"\nStats: {stats}")
    print(f"Time taken to stop: {end - start:.2f} seconds")

    # If it was successfully killed, the `execute_powershell` should return quickly
    # and print an error or timeout, NOT wait the full 30 seconds.
    await task
    print("\nTest Finished! If it didn't hang for 30 seconds, it WORKED!")

if __name__ == "__main__":
    asyncio.run(test_estop())
