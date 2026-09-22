"""
INTELLIGENT SECURITY GUARD — inspired by panel scanner design
────────────────────────────────────────────────────────────
Philosophy (from example panel):
  • Normal Telegram bots (telebot / requests / send_document for OWN users) = SAFE
  • Only REAL data theft + backdoors cause auto-REJECT
  • Hardcoded bot token alone = soft warn, not block
  • os.walk without system paths = OK
  • os.walk('/root'|'/etc'|'/home') + zip/send = STEALER → block

Score rules:
  has_blocking (Data Theft / Backdoor) AND score >= 70 → REJECT
  score >= 85 → REJECT
  else soft / approve
"""
from __future__ import annotations
import os, re, ast, zipfile, logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

logger = logging.getLogger('APON.security.guard')


# ═══════════════════════════════════════════════════
#  CATEGORY PATTERNS (example-panel style)
# ═══════════════════════════════════════════════════
SEC_PATTERNS: Dict[str, List[Tuple[str, str]]] = {
    # Real data theft — system dirs / credential files / stealer fingerprints
    "Data Theft": [
        (r'os\.walk\s*\(\s*["\'][/\\](?:root|home|etc|var|proc)["\']',
         "system directory walk"),
        (r'os\.walk\s*\(',
         "os.walk (dir traversal)"),
        (r'open\s*\(\s*["\']/etc/(?:passwd|shadow|sudoers)["\']',
         "reading /etc/passwd|shadow"),
        (r'open\s*\(\s*["\']/root/',
         "reading /root"),
        (r'/proc/self/environ',
         "env exfiltration"),
        (r'/proc/\d+/mem',
         "process memory read"),
        (r'\.ssh/(?:id_rsa|id_dsa|authorized_keys|known_hosts)',
         "SSH key access"),
        (r'\.aws/credentials',
         "AWS credentials"),
        (r'["\']\.\./\.\.|["\']\.\./\.\./',
         "parent dir traversal ../../"),
        (r'/home/container|/home/runner',
         "hosting container path probe"),
        (r'endswith\s*\([^)]*\.env',
         "collecting .env files"),
        (r'api\.telegram\.org/bot.*/sendDocument',
         "telegram sendDocument API exfil"),
        (r'secret_files\.zip|grab_everything|jaleb files|tejelbou',
         "known stealer markers"),
        (r'potential_paths\s*=',
         "multi-path stealer probe list"),
        (r'glob\.glob\s*\(["\'][/\\]\*',
         "root glob scan"),
        (r'shutil\.copy.*["\'][/\\]root',
         "/root copy"),
        (r'ROOT_DIR\s*=\s*["\'][/\\]["\']',
         "ROOT_DIR = /"),
    ],
    "Backdoor": [
        (r'eval\s*\(\s*(?:base64\.b64decode|bytes\.fromhex|codecs\.decode)',
         "eval decoded bytecode"),
        (r'exec\s*\(\s*(?:base64\.b64decode|bytes\.fromhex|codecs\.decode)',
         "exec decoded bytecode"),
        (r'marshal\.loads\s*\(',
         "marshal.loads"),
        (r"__import__\s*\(\s*['\"]os['\"]\s*\)\s*\.\s*system",
         "__import__('os').system"),
        (r'subprocess\s*\.\s*(?:Popen|call|run)\s*\([^\n]*shell\s*=\s*True[^\n]*(?:input|stdin)',
         "shell injection with user input"),
        (r'os\.system\s*\(\s*[\'"][^\'"]*(?:curl|wget|nc|netcat|bash|sh)\s',
         "os.system download/shell"),
        (r':\(\)\s*\{\s*:\|:&\s*\}\s*;',
         "fork bomb"),
        (r'while\s+True\s*:\s*os\.fork\s*\(',
         "infinite fork"),
        (r'nc\s+-e\s+/bin/(?:sh|bash)',
         "netcat reverse shell"),
        (r'bash\s+-i\s+>&\s*/dev/tcp/',
         "bash reverse shell"),
        (r'python\s+-c\s+[\'"]import\s+socket[^\'"]*dup2',
         "python reverse shell"),
        (r'socket\.socket[^\n]*connect[^\n]*dup2',
         "socket dup2 shell"),
        (r'os\.setuid\s*\(\s*0\s*\)',
         "setuid(0)"),
        (r'ctypes\.CDLL\s*\(\s*[\'"]libc',
         "libc via ctypes"),
        (r'xmrig|minerd|cryptonight',
         "crypto miner"),
        (r'stratum\+tcp://',
         "mining pool"),
    ],
    "Obfuscation": [
        (r'base64\.b64decode\s*\(.*\)\s*[\)\s]*\bexec\b',
         "base64 + exec"),
        (r'(?:\\x[0-9a-fA-F]{2}){6,}',
         "long hex obfuscation"),
        (r'zlib\.decompress\s*\(.*\)\s*[\)\s]*\bexec\b',
         "zlib + exec"),
    ],
    "Suspicious Network": [
        (r'devil-api\.com|elementfx\.io',
         "known malicious endpoint"),
        (r'open\s*\(\s*["\'][/\\](?:root|etc|proc|sys).*(?:requests|urllib).*(?:post|put)',
         "system file HTTP POST"),
        (r'pastebin\.com/raw',
         "pastebin raw fetch"),
    ],
    "Resource Abuse": [
        (r'multiprocessing\.Pool\s*\(\s*(?:None|\d{3,})',
         "massive process pool"),
        (r'fork\s*\(\s*\).*fork\s*\(',
         "fork bomb pattern"),
    ],
}

# Combo patterns that prove stealer intent (high weight)
STEALER_COMBOS: List[Tuple[str, str, str]] = [
    (r'\bos\.walk\b', r'zipfile\.ZipFile', "os.walk + ZIP"),
    (r'\bos\.walk\b', r'api\.telegram\.org', "os.walk + telegram API"),
    (r'\bos\.walk\b', r'requests\.(?:post|get)', "os.walk + HTTP"),
    (r'\bos\.walk\b', r'send_document', "os.walk + send_document"),
    (r'zipfile\.ZipFile', r'api\.telegram\.org', "ZIP + telegram exfil"),
    (r'zipfile\.ZipFile', r'requests\.(?:post|get)', "ZIP + HTTP upload"),
    (r'\.env', r'zipfile\.ZipFile', ".env + ZIP"),
    (r'\.env', r'api\.telegram\.org', ".env + telegram"),
    (r'/home/container|/home/runner|\.\./\.\.', r'os\.walk', "container path + walk"),
    (r'endswith\s*\([^)]*\.env', r'os\.walk', ".env collect + walk"),
]

SAFE_HINTS = [
    r'\btelebot\.TeleBot\s*\(', r'\bfrom\s+telebot\b',
    r'@bot\.message_handler', r'@bot\.callback_query_handler',
    r'\bbot\.infinity_polling\s*\(', r'\bbot\.polling\s*\(',
    r'ApplicationBuilder\(\)', r'\bfrom\s+aiogram\b', r'\bfrom\s+pyrogram\b',
]

BOT_TOKEN_RE = re.compile(r'\b\d{8,10}:AA[A-Za-z0-9_-]{33}\b')

WEIGHTS = {
    "Data Theft":          40,
    "Backdoor":            40,
    "Obfuscation":         10,
    "Suspicious Network":  12,
    "Resource Abuse":       8,
    "Exposed Credentials": 10,
}


def _static_scan(code: str) -> Dict[str, List[str]]:
    results: Dict[str, List[str]] = {}
    for category, pattern_list in SEC_PATTERNS.items():
        hits = []
        for pattern, description in pattern_list:
            try:
                if re.search(pattern, code, re.IGNORECASE | re.MULTILINE):
                    hits.append(description)
            except re.error:
                continue
        if hits:
            results[category] = hits
    tokens = BOT_TOKEN_RE.findall(code)
    if tokens:
        results.setdefault("Exposed Credentials", [])
        results["Exposed Credentials"].append(f"bot token: {tokens[0][:15]}...")
    return results


def _combo_scan(code: str) -> List[str]:
    hits = []
    for a_re, b_re, desc in STEALER_COMBOS:
        try:
            if re.search(a_re, code, re.IGNORECASE) and re.search(b_re, code, re.IGNORECASE):
                hits.append(desc)
        except re.error:
            continue
    return hits


def _ast_scan(code: str) -> List[str]:
    findings: List[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"syntax error (possible obfuscation): {e}"]
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # os.walk('/root'|'/etc'|...)
        if isinstance(func, ast.Attribute):
            if (func.attr == 'walk' and isinstance(func.value, ast.Name)
                    and func.value.id == 'os' and node.args):
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if arg.value in ('/', '/root', '/etc', '/home', '/proc', '/var'):
                        findings.append(f"os.walk('{arg.value}') sensitive dir")
            if isinstance(func.value, ast.Name):
                if func.value.id == 'os' and func.attr in (
                        'system', 'popen', 'fork', 'setuid', 'setgid',
                        'execv', 'execve', 'execl'):
                    # only note; low weight later unless paired
                    pass
                if func.value.id == 'subprocess' and func.attr in (
                        'Popen', 'call', 'run', 'check_output'):
                    pass
        # eval/exec with dynamic argument
        if isinstance(func, ast.Name) and func.id in ('eval', 'exec'):
            if node.args:
                arg0 = node.args[0]
                if isinstance(arg0, (ast.Call, ast.Attribute, ast.Name)):
                    findings.append(f"dynamic {func.id}()")
        # __import__('os')
        if isinstance(func, ast.Name) and func.id == '__import__':
            if node.args and isinstance(node.args[0], ast.Constant):
                if node.args[0].value in ('os', 'subprocess', 'ctypes'):
                    findings.append(f"dynamic __import__('{node.args[0].value}')")
        # sensitive path string constants
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for sensitive in ('/etc/passwd', '/etc/shadow', '/root/',
                              '/proc/self/environ', '.ssh/id_rsa', '.aws/credentials'):
                if sensitive in node.value:
                    findings.append(f"sensitive path '{sensitive}'")
    return list(dict.fromkeys(findings))


def _calculate_risk(static: dict, combos: List[str], ast_findings: List[str]) -> int:
    score = 0
    for cat, hits in static.items():
        if not hits:
            continue
        w = WEIGHTS.get(cat, 5)
        score += w * min(len(hits), 3)
    # stealer combos are strong signal
    score += min(len(combos) * 25, 75)
    unique_ast = list(dict.fromkeys(ast_findings))
    score += min(len(unique_ast) * 5, 20)
    return min(score, 100)


def _get_verdict(risk: int, static: dict, combos: List[str]) -> Tuple[str, str, bool]:
    """Returns (verdict, recommendation, has_critical)."""
    has_theft = bool(static.get("Data Theft"))
    has_backdoor = bool(static.get("Backdoor"))
    has_blocking = has_theft or has_backdoor or bool(combos)
    has_creds = bool(static.get("Exposed Credentials"))

    # Stealer combos alone are enough to block at moderate score
    if combos and risk >= 50:
        return "DANGEROUS", "REJECT", True
    if has_blocking and risk >= 70:
        return "DANGEROUS", "REJECT", True
    if risk >= 85:
        return "DANGEROUS", "REJECT", True
    # Hardcoded token alone is bad practice but common — do NOT block
    if has_creds and not has_blocking and risk < 40:
        return "SAFE", "APPROVE", False
    if has_blocking and risk >= 40:
        return "SUSPICIOUS", "MANUAL_REVIEW", True
    if risk >= 55:
        return "SUSPICIOUS", "MANUAL_REVIEW", False
    return "SAFE", "APPROVE", False


def scan_source(code: str, filename: str = "file.py") -> Dict[str, Any]:
    static = _static_scan(code)
    combos = _combo_scan(code)
    af = _ast_scan(code)
    risk = _calculate_risk(static, combos, af)

    # Soften if looks like a normal Telegram bot
    safe_matches = sum(1 for sp in SAFE_HINTS if re.search(sp, code))
    if safe_matches >= 2 and not combos:
        risk = max(0, risk - 30)

    verdict, rec, has_critical = _get_verdict(risk, static, combos)

    threats: List[str] = []
    for cat, hits in static.items():
        for h in hits:
            threats.append(f"{cat}: {h}")
    threats.extend(combos)
    threats.extend(af[:5])

    if verdict == "DANGEROUS":
        # surface as high score for UI
        risk = max(risk, 90)

    return {
        "verdict": verdict,
        "risk_score": risk,
        "recommendation": rec,
        "all_threats": threats[:20],
        "filename": filename,
        "has_critical": has_critical,
        "summary": f"{verdict} (score={risk}, threats={len(threats)}, critical={has_critical})",
    }


def scan_file_path(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {"verdict": "ERROR", "risk_score": 0, "recommendation": "APPROVE",
                "all_threats": [f"missing: {path}"], "filename": p.name,
                "has_critical": False, "summary": "missing"}
    if p.suffix.lower() not in ('.py', '.js', '.mjs', '.cjs', '.ts', '.sh', '.bash'):
        return {"verdict": "SAFE", "risk_score": 0, "recommendation": "APPROVE",
                "all_threats": [], "filename": p.name, "has_critical": False,
                "summary": "non-source skipped"}
    try:
        code = p.read_text(errors='ignore')
    except Exception as e:
        return {"verdict": "ERROR", "risk_score": 50, "recommendation": "MANUAL_REVIEW",
                "all_threats": [f"read error: {e}"], "filename": p.name,
                "has_critical": False, "summary": "read failed"}
    return scan_source(code, p.name)


def scan_zip_path(zip_path: str) -> Dict[str, Any]:
    results = []
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            for info in z.infolist():
                name = info.filename
                if name.startswith('/') or '..' in name.split('/'):
                    return {"verdict": "DANGEROUS", "risk_score": 99,
                            "recommendation": "REJECT", "has_critical": True,
                            "all_threats": [f"Zip Slip: {name}"],
                            "filename": os.path.basename(zip_path), "summary": "Zip Slip"}
                if Path(name).suffix.lower() not in ('.py', '.js', '.mjs', '.cjs',
                                                     '.ts', '.sh', '.bash'):
                    continue
                try:
                    code = z.read(info).decode('utf-8', errors='ignore')
                except Exception:
                    continue
                results.append(scan_source(code, name))
    except zipfile.BadZipFile:
        return {"verdict": "SUSPICIOUS", "risk_score": 25,
                "recommendation": "MANUAL_REVIEW", "has_critical": False,
                "all_threats": ["not a valid ZIP"],
                "filename": os.path.basename(zip_path), "summary": "bad zip"}
    if not results:
        return {"verdict": "SAFE", "risk_score": 0, "recommendation": "APPROVE",
                "all_threats": [], "filename": os.path.basename(zip_path),
                "has_critical": False, "summary": "no source"}
    return max(results, key=lambda r: r["risk_score"])


def scan_directory_recursive(root: str, reject_threshold: int = 70) -> Dict[str, Any]:
    root_p = Path(root)
    results = []
    for f in root_p.rglob('*'):
        if not f.is_file():
            continue
        if any(part in ('.deps', 'node_modules', '.tmp_run', '__pycache__',
                        '.git', 'venv', '.venv', '.home') for part in f.parts):
            continue
        if f.suffix.lower() not in ('.py', '.js', '.mjs', '.cjs', '.ts', '.sh', '.bash'):
            continue
        try:
            if f.stat().st_size > 5 * 1024 * 1024:
                continue
        except OSError:
            continue
        try:
            r = scan_file_path(str(f))
            results.append((f, r))
        except Exception:
            continue
    if not results:
        return {"ok": True, "worst": None, "scanned": 0, "summary": "no source"}
    worst_f, worst = max(results, key=lambda x: x[1].get("risk_score", 0))
    worst = {**worst, "path": str(worst_f.relative_to(root_p))}
    # Fail only when critical + high enough score
    ok = not (worst.get("has_critical") and worst.get("risk_score", 0) >= reject_threshold)
    return {"ok": ok, "worst": worst, "scanned": len(results),
            "summary": (f"scanned={len(results)} worst={worst.get('verdict')} "
                        f"score={worst.get('risk_score')} critical={worst.get('has_critical')}")}
