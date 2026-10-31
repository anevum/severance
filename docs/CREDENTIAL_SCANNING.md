# Targeted Git history scan

CI runs `python3 scripts/scan-git-history.py` after a full-depth checkout. The
scanner checks selected credential formats in text blobs reachable from the
local Git refs. It reports only the object ID and rule name; it does not print
the matching value. A match fails the check. If a real credential is exposed,
revoke or rotate it through the appropriate private process; do not paste the
value into an issue or pull request.

This is a limited guard, not a comprehensive secret or privacy audit. It does
not inspect binary files and cannot scan refs absent from the local checkout.
GitHub Actions checkout does not necessarily include every remote branch. Scan
those separately before claiming repository-wide coverage. The checks do not
prove that credentials are valid or that personal data is absent.

The scanner and its synthetic history tests require Python 3 and Git:

```sh
python3 -m unittest scripts/test_scan_git_history.py
python3 scripts/scan-git-history.py
```
