const fs = require('fs');
const path = require('path');

function searchInDir(dir) {
  const files = fs.readdirSync(dir);
  for (const file of files) {
    if (file === 'node_modules' || file === '.git' || file === '.venv') continue;
    const fullPath = path.join(dir, file);
    const stat = fs.statSync(fullPath);
    if (stat.isDirectory()) {
      searchInDir(fullPath);
    } else {
      if (['.js', '.ts', '.tsx', '.py', '.html', '.css', '.json'].some(ext => fullPath.endsWith(ext))) {
        const content = fs.readFileSync(fullPath, 'utf8');
        if (content.toLowerCase().includes('vioce')) {
          console.log(fullPath);
        }
      }
    }
  }
}

searchInDir('.');
