# Pipeline Image Format Recovery (draft stage)

## Trigger
`draft` stage fails with:
- `图片内容格式无法识别：imgs/NN-*.png`
- `图片声明格式 image/png 与实际格式 image/jpeg 不一致：imgs/NN-*.png`
- 0-byte files or magic bytes mismatch after `image_generate` + `curl` save.

Root cause: `wechat_publish.py:read_image()` + `_detected_image_type()` enforces strict magic-byte detection vs extension/declared type. xAI `image_generate` often returns JPEG payload even when URL ends in `.png`; curl preserves it; PIL `Image.open().save(..., "PNG")` fixes.

## Recovery Steps (existing worktree, no `init`)
1. Confirm images under `work/<acct>/current/imgs/`.
2. Use system `python3` + PIL (always present) to force real PNG:
   ```bash
   python3 -c '
   from PIL import Image
   import os
   for f in ["imgs/01-*.png", "imgs/02-*.png"]:
       with Image.open(f) as im:
           if im.mode in ("RGBA", "P"): im = im.convert("RGB")
           im.save(f, "PNG", optimize=True)
       print(f, "→ PNG", os.path.getsize(f))
   '
   ```
3. Reset draft (clears `details` + `outcome=uncertain`):
   ```bash
   python3 .../pipeline_job.py stage --job work/<acct>/current/job.json \
     --name draft --status pending --message "已修复图片格式，重新尝试"
   ```
4. Rerun only the finish step (reuses all prior artifacts):
   ```bash
   python3 .../pipeline_runtime.py finish --job .../job.json --config wechat-accounts.json
   ```
5. Verify: `job.json` state=`drafted`, `draft-result.json` exists with `draft_media_id`, `stages.draft.status=completed`.

## Pitfalls
- Never `init --force-new` on a running/failed job that already has valid `article.md` + illustrations.
- Do not edit HTML or article.md paths; keep original `.png` names after conversion.
- The `pending` reset is the only way to clear `retry_safe=false`; manual `job.json` edit is forbidden.
- Always re-verify with `python3 -c "from PIL import Image; print(Image.open(f).format)"` before retry.

This pattern applies to any `image_generate` backend that returns non-native format for the declared extension.