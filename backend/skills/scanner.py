import ast
from typing import List

class SecurityScanner(ast.NodeVisitor):
    def __init__(self):
        self.violations: List[str] = []
        # List of dangerous functions we want to block in plugins
        self.dangerous_functions = {
            'eval', 'exec', 'compile', '__import__',
            'system', 'popen', 'subprocess', 'pickle',
            'socket', 'Popen', 'call', 'check_output',
            'run', 'os', 'sys', 'open', 'breakpoint',
            'getattr', 'setattr', 'delattr', '__builtins__'
        }
        
    def visit_Call(self, node):
        # Check if the function being called is a Name (e.g., eval())
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name in self.dangerous_functions:
                self.violations.append(f"Direct call to dangerous function: {func_name}")
                
        # Check if the function is an Attribute (e.g., subprocess.Popen)
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
            if func_name in self.dangerous_functions:
                self.violations.append(f"Attribute call to dangerous function: {func_name}")
            
            # Also check the base module name (e.g., subprocess.run)
            if isinstance(node.func.value, ast.Name):
                module_name = node.func.value.id
                if module_name in self.dangerous_functions:
                    self.violations.append(f"Call from dangerous module: {module_name}")
                    
        self.generic_visit(node)
        
    def visit_Import(self, node):
        for alias in node.names:
            if alias.name in self.dangerous_functions:
                self.violations.append(f"Import of dangerous module: {alias.name}")
        self.generic_visit(node)
        
    def visit_ImportFrom(self, node):
        if node.module in self.dangerous_functions:
            self.violations.append(f"Import from dangerous module: {node.module}")
        self.generic_visit(node)

def scan_plugin_code(code_str: str) -> bool:
    """
    Scans python code for security violations.
    Returns True if safe, raises Exception if violations found.
    """
    try:
        tree = ast.parse(code_str)
    except SyntaxError as e:
        raise ValueError(f"Syntax error in plugin code: {e}")
        
    scanner = SecurityScanner()
    scanner.visit(tree)
    
    if scanner.violations:
        raise SecurityError(f"Security violations found: {', '.join(scanner.violations)}")
        
    return True

class SecurityError(Exception):
    pass
