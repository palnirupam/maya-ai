import os
import shutil
import glob

def create_file(filepath: str, content: str) -> str:
    """
    Creates a new file at the specified absolute path with the given content.
    If the directory does not exist, it will be created.
    """
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"SUCCESS: File created at {filepath}"
    except Exception as e:
        return f"ERROR: Failed to create file {filepath}. {e}"

def read_file(filepath: str) -> str:
    """
    Reads the content of a file at the specified absolute path.
    """
    try:
        if not os.path.exists(filepath):
            return f"ERROR: File {filepath} does not exist."
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        return content
    except Exception as e:
        return f"ERROR: Failed to read file {filepath}. {e}"

def list_directory(directory_path: str) -> str:
    """
    Lists the contents of the specified directory.
    """
    try:
        if not os.path.exists(directory_path):
            return f"ERROR: Directory {directory_path} does not exist."
        
        items = os.listdir(directory_path)
        return f"Contents of {directory_path}:\n" + "\n".join(items)
    except Exception as e:
        return f"ERROR: Failed to list directory {directory_path}. {e}"

def delete_file(filepath: str) -> str:
    """
    Deletes the file at the specified absolute path. Use with extreme caution.
    """
    try:
        if not os.path.exists(filepath):
            return f"ERROR: File {filepath} does not exist."
        os.remove(filepath)
        return f"SUCCESS: Deleted {filepath}"
    except Exception as e:
        return f"ERROR: Failed to delete {filepath}. {e}"


def search_local_files(query: str, root_path: str = None) -> str:
    """
    Recursively searches for files matching a query string in their name on the PC.
    Highly optimized: automatically skips heavy system folders (like AppData, node_modules, .git) for speed.
    Args:
        query (str): The filename or part of the name to search for (e.g. "report", "syllabus.pdf").
        root_path (str, optional): The directory path to search under. Defaults to the User's Home Profile directory (C:\\Users\\username).
    """
    import os
    if not root_path:
        root_path = os.path.expanduser("~") # Defaults to C:\Users\username
        
    if not os.path.exists(root_path):
        return f"ERROR: Search directory '{root_path}' does not exist."
        
    query_lower = query.lower().strip()
    matches = []
    max_results = 25
    
    # Folders to completely skip for speed and security
    skip_dirs = {
        'appdata', 'node_modules', '.git', '.venv', 'env', 'venv', 
        'temp', 'tmp', 'cache', 'system32', 'windows', 'documents and settings'
    }
    
    try:
        for root, dirs, files in os.walk(root_path):
            # Modify dirs in-place to prune heavy and system directories
            dirs[:] = [d for d in dirs if d.lower() not in skip_dirs and not d.startswith('.')]
            
            for file in files:
                if query_lower in file.lower():
                    full_path = os.path.join(root, file)
                    matches.append(full_path)
                    if len(matches) >= max_results:
                        break
            if len(matches) >= max_results:
                break
                
        if not matches:
            return f"No files found matching '{query}' under '{root_path}'."
            
        results_str = f"Found {len(matches)} files matching '{query}':\n"
        results_str += "\n".join(f"- {path}" for path in matches)
        return results_str
    except Exception as e:
        return f"ERROR: File search failed. {e}"

