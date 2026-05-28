"""
Maya AI — Google Classroom Integration
Automates fetching assignments and uploading files to Google Classroom.
"""
import os
import logging
import asyncio
from backend.tools.desktop.advanced.playwright_browser import browser_manager

logger = logging.getLogger(__name__)

async def classroom_list_assignments(class_name: str = "") -> str:
    """
    Opens Google Classroom and lists pending assignments.
    Args:
        class_name (str): Optional. If provided, filters to a specific class.
    """
    try:
        await browser_manager.start(headless=False)
        page = browser_manager.page
        
        await page.goto("https://classroom.google.com/h", wait_until="load")
        await asyncio.sleep(4)
        
        # Check if login is required
        if "accounts.google.com" in page.url:
            return "ERROR: You need to log in to your Google Account first. I have opened the browser for you to log in."
            
        if class_name:
            # Try to click the class
            cls_link = page.get_by_text(class_name)
            if await cls_link.count() > 0:
                await cls_link.first.click()
                await asyncio.sleep(3)
                await page.goto(page.url + "/a", wait_until="load") # Go to classwork
            else:
                return f"ERROR: Could not find class '{class_name}'. Make sure the name is correct."
        else:
            # Go to global To-Do list
            await page.goto("https://classroom.google.com/a/not-turned-in/all", wait_until="load")
            
        await asyncio.sleep(3)
        await browser_manager.save_state()
        
        # We extract content using our standard get_content to let Gemini read it
        from backend.tools.desktop.advanced.playwright_browser import playwright_get_content
        return f"SUCCESS: Opened assignments for {class_name or 'All Classes'}. Page content:\n\n{await playwright_get_content()}"
        
    except Exception as e:
        return f"ERROR listing assignments: {e}"

async def classroom_upload_file(assignment_url_or_name: str, file_path: str) -> str:
    """
    Uploads a file to a specific Google Classroom assignment and submits it.
    Args:
        assignment_url_or_name (str): The direct URL to the assignment, or the exact text name of the assignment to click.
        file_path (str): The absolute path to the file to upload (e.g. 'C:/Users/palni/Documents/homework.pdf').
    """
    if not os.path.exists(file_path):
        # Try to find it in the user's workspace
        return f"ERROR: File '{file_path}' does not exist on disk."
        
    try:
        await browser_manager.start(headless=False)
        page = browser_manager.page
        
        if assignment_url_or_name.startswith("http"):
            await page.goto(assignment_url_or_name, wait_until="load")
        else:
            # Assume we are already on the classwork page and need to click it
            item = page.get_by_text(assignment_url_or_name)
            if await item.count() > 0:
                await item.first.click()
                # Click 'View assignment' if it's a dropdown
                view_btn = page.get_by_text("View assignment")
                if await view_btn.count() > 0:
                    await view_btn.first.click()
            else:
                return f"ERROR: Could not find assignment '{assignment_url_or_name}' on the current page."
                
        await asyncio.sleep(3)
        
        # Click "+ Add or create"
        add_btn = page.get_by_text("Add or create")
        if await add_btn.count() == 0:
            return "ERROR: Could not find the '+ Add or create' button. Have you already submitted this assignment?"
            
        await add_btn.first.click()
        await asyncio.sleep(1)
        
        # Click "File"
        file_btn = page.get_by_text("File", exact=True)
        if await file_btn.count() > 0:
            await file_btn.first.click()
        else:
            return "ERROR: Could not find the 'File' upload option."
            
        await asyncio.sleep(2)
        
        # Google uses an iframe or hidden file input for the Google Drive picker
        # Playwright can intercept file choosers
        async with page.expect_file_chooser() as fc_info:
            # Click the Browse button inside the dialog
            browse_btn = page.get_by_text("Browse")
            if await browse_btn.count() > 0:
                await browse_btn.first.click()
            else:
                return "ERROR: Could not find the 'Browse' button in the file upload dialog."
                
        file_chooser = await fc_info.value
        await file_chooser.set_files(file_path)
        
        await asyncio.sleep(5) # Wait for upload to complete
        
        # Click Turn In
        turn_in_btn = page.get_by_role("button", name="Turn in")
        if await turn_in_btn.count() > 0:
            await turn_in_btn.first.click()
            await asyncio.sleep(1)
            # Confirm Turn in
            confirm_btn = page.locator("div[role='dialog']").get_by_role("button", name="Turn in")
            if await confirm_btn.count() > 0:
                await confirm_btn.first.click()
                
            await browser_manager.save_state()
            return f"SUCCESS: Uploaded '{os.path.basename(file_path)}' and turned in the assignment!"
        else:
            await browser_manager.save_state()
            return f"SUCCESS: Uploaded '{os.path.basename(file_path)}' successfully, but could not find the final 'Turn in' button. Please click it manually."
            
    except Exception as e:
        return f"ERROR uploading to Google Classroom: {e}"
