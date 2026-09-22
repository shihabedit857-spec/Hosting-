"""
GITHUB HELPER — Parse URL + download repo zipball
"""

import re
import requests
import logging

logger = logging.getLogger('APON.github')


def parse_github_url(url: str):
    """
    Parse a GitHub URL → (owner, repo, branch)
    Examples:
      https://github.com/user/repo
      https://github.com/user/repo.git
      https://github.com/user/repo/tree/dev
    """
    url = (url or '').strip()
    url = re.sub(r'\.git$', '', url)
    if 'github.com' not in url:
        raise ValueError("Not a valid GitHub URL")

    parts = url.split('github.com/')[-1].split('/')
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise ValueError("Invalid GitHub URL format")

    owner  = parts[0]
    repo   = parts[1]
    branch = 'main'

    if len(parts) >= 4 and parts[2] == 'tree':
        branch = parts[3]
    elif len(parts) >= 4 and parts[2] == 'blob':
        branch = parts[3]

    return owner, repo, branch


def download_github_repo(owner, repo, branch='main', token=None, max_mb=50):
    """
    Download the repo as a zipball via GitHub API.
    Returns: bytes of the ZIP (max max_mb megabytes).
    Raises: Exception with friendly message on failure.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/zipball/{branch}"
    headers = {'Accept': 'application/vnd.github+json'}
    if token:
        headers['Authorization'] = f'token {token}'

    try:
        resp = requests.get(url, headers=headers, stream=True, timeout=60)
    except requests.exceptions.Timeout:
        raise Exception("GitHub request timed out")
    except requests.exceptions.ConnectionError:
        raise Exception("Cannot reach GitHub — check server internet")

    if resp.status_code == 404:
        raise Exception("Repository or branch not found (or private repo without token)")
    if resp.status_code == 401:
        raise Exception("Invalid GitHub token (401 Unauthorized)")
    if resp.status_code == 403:
        raise Exception("GitHub rate limit / forbidden (403)")
    if resp.status_code != 200:
        raise Exception(f"GitHub API error: HTTP {resp.status_code}")

    cl = resp.headers.get('content-length')
    if cl and int(cl) > max_mb * 1024 * 1024:
        raise Exception(f"Repository ZIP exceeds {max_mb}MB limit")

    buf = bytearray()
    limit = max_mb * 1024 * 1024
    for chunk in resp.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        buf.extend(chunk)
        if len(buf) > limit:
            raise Exception(f"Repository ZIP exceeds {max_mb}MB limit")

    return bytes(buf)