# Tool downloader provenance and fail-closed RDTE

Original synthetic ZIP and local file URLs only. Test valid SHA, missing URL transport failure, digest mismatch, invalid source spec and no destination writes on denial.

Changes: curl --fail --show-error --silent --location with bounded retry/timeouts; ephemeral downloaded ZIP under a cleanup trap; digest check before destination creation. The existing AutoIt and Python special handling remains.

No real WinInspect release asset or tool package is downloaded by this workflow; its purpose is transport/error classification, not release admission. Pinned dependency URLs and checksums remain unchanged and require separate provenance review.

Owner DLE mark-e-deyoung/winebot-research#3. This branch is a source candidate, not permission to merge, publish or deploy.