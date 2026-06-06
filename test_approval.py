import asyncio
import os
import json
from backend.brain.reasoning.tool_planner import tool_planner
from backend.database.models import PendingApproval
from backend.database.connection import SessionLocal

async def run_test():
    print("Testing Exec Approval System...")

    # 1. Test Queueing
    tool_name = "execute_powershell"
    payload = {"command": "rm -rf C:/test"}
    print(f"Queueing tool: {tool_name} with {payload}")
    
    req_data = tool_planner.queue_tool(tool_name, payload)
    req_id = req_data["request_id"]
    risk = req_data["risk_level"]
    print(f"Queued! ID: {req_id}, Risk: {risk}")
    assert risk == "CRITICAL", f"Expected CRITICAL, got {risk}"

    # 2. Verify it is in DB
    db = SessionLocal()
    db_req = db.query(PendingApproval).filter_by(request_id=req_id).first()
    assert db_req is not None, "Failed to save to SQLite!"
    assert db_req.status == "pending", "Status not pending!"
    db.close()
    print("SQLite Save: OK")

    # 3. Simulate resolving the tool
    # We will trigger the resolution in a background task so wait_for_approval unblocks
    async def approver():
        await asyncio.sleep(1)
        tool_planner.resolve_tool(req_id, approved=True, user_id="test_admin")

    asyncio.create_task(approver())

    print("Waiting for approval...")
    approved = await tool_planner.wait_for_approval(req_id)
    assert approved is True, "Approval failed!"
    print("Approval: OK")

    # 4. Verify DB is updated
    db = SessionLocal()
    db_req = db.query(PendingApproval).filter_by(request_id=req_id).first()
    assert db_req.status == "approved", "Status not updated in DB!"
    db.close()
    print("SQLite Update: OK")

    # 5. Verify Audit Log
    log_path = os.path.join("logs", "audit.jsonl")
    assert os.path.exists(log_path), "Audit log not created!"
    
    found = False
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line.strip())
            if entry.get("request_id") == req_id:
                assert entry["approved"] is True
                assert entry["approved_by"] == "test_admin"
                assert entry["risk"] == "CRITICAL"
                found = True
                break
    assert found, "Audit log entry not found!"
    print("Audit Logger: OK")

    print("\n✅ All tests passed! Phase 1 is perfectly stable.")

if __name__ == "__main__":
    asyncio.run(run_test())
