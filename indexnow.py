"""Tell Bing and other IndexNow engines which pages changed in the latest commit.

Usage: python indexnow.py [BASE_REF]   (default HEAD~1; the pages changed between BASE_REF and HEAD are sent)
Run after a successful upload in collect.sh. It never fails the collection run: any problem is printed and ignored.
The key file (<key>.txt at the site root) proves the site is ours. Docs: https://www.indexnow.org/documentation
"""
import glob, json, os, subprocess, sys
import requests

HOST = "gigsnshows.com"
ROOT = os.path.dirname(os.path.abspath(__file__))
SKIP = {"404.html", "contact.html", "privacy.html", "terms.html"}

def key():
    for p in glob.glob(os.path.join(ROOT, "*.txt")):
        name = os.path.basename(p)[:-4]
        if len(name) == 32 and all(c in "0123456789abcdef" for c in name):
            return name
    return None

def changed_urls(base):
    out = subprocess.run(["git", "-C", ROOT, "diff", "--name-only", base, "HEAD"], capture_output=True, text=True).stdout
    urls = []
    for f in out.splitlines():
        if not f.endswith("index.html") and f not in ("index.html",) or f in SKIP:
            continue
        d = f[: -len("index.html")]
        urls.append(f"https://{HOST}/{d}")
    return sorted(set(urls))

def main():
    k = key()
    if not k:
        print("indexnow: no key file found, skipping"); return
    urls = changed_urls(sys.argv[1] if len(sys.argv) > 1 else "HEAD~1")[:10000]
    if not urls:
        print("indexnow: no changed pages"); return
    body = {"host": HOST, "key": k, "keyLocation": f"https://{HOST}/{k}.txt", "urlList": urls}
    try:
        r = requests.post("https://api.indexnow.org/indexnow", json=body, timeout=30)
        print(f"indexnow: sent {len(urls)} urls, status {r.status_code}")
    except Exception as e:
        print(f"indexnow: could not send ({e})")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"indexnow: skipped ({e})")
