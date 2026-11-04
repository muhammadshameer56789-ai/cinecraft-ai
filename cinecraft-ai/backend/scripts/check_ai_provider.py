"""Smoke-test the configured AI provider with YOUR key (the adapter has not been run against the live service by the authors).
Usage:  AI_PROVIDER=openai AI_API_KEY=sk-... python scripts/check_ai_provider.py [photo.jpg]"""
import io
import sys
import time

sys.path.insert(0, ".")
from PIL import Image  # noqa: E402

from app.services import engine  # noqa: E402
from app.services.ai import canvas, guard  # noqa: E402
from app.services.ai.base import ProviderError  # noqa: E402
from app.services.ai.openai_provider import get_provider  # noqa: E402
from app.services.ai.prompts import build_prompt  # noqa: E402

p = get_provider()
if p is None:
    sys.exit("No provider configured. Set AI_PROVIDER and AI_API_KEY (see .env.example).")
if len(sys.argv) > 1:
    src = Image.open(sys.argv[1]).convert("RGB")
else:
    src = Image.new("RGB", (768, 512), (90, 120, 80))
src.thumbnail((1536, 1536))
c = canvas.pick_canvas(*src.size)
img, box = canvas.to_canvas(src, c)
buf = io.BytesIO(); img.save(buf, "PNG")
prompt = build_prompt("golden_hour", 80, None, c)
t = time.time()
try:
    raw = p.edit(buf.getvalue(), prompt, c)
except ProviderError as e:
    sys.exit(f"FAILED ({e.kind}): {e}")
out = canvas.from_canvas(Image.open(io.BytesIO(raw)), c, box, src.size)
print(f"OK in {time.time() - t:.1f}s; composition similarity {guard.composition_similarity(src, out):.2f} "
      f"(job minimum {guard.config.AI_MIN_SIMILARITY})")
out.save("ai_check_output.jpg"); print("wrote ai_check_output.jpg: inspect it for identity and framing")
