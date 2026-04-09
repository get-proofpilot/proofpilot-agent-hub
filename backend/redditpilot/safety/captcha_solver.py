"""Reddit CAPTCHA auto-solver using open-source OCR libraries.

Reddit's old-style CAPTCHA: distorted text image served at
  https://www.reddit.com/captcha/{iden}
When a POST fails with BAD_CAPTCHA, retry with captcha_iden + captcha_sol.

Solver priority chain:
  1. ddddocr   -- purpose-built deep-learning CAPTCHA OCR (best accuracy)
  2. tesseract -- traditional OCR fallback (pytesseract + PIL pre-processing)
  3. None      -- give up, apply cooldown

Install: pip install ddddocr pillow
Optional: apt install tesseract-ocr && pip install pytesseract
"""

import io
import logging
import time
from typing import Optional

import requests

logger = logging.getLogger("redditpilot.captcha_solver")

CAPTCHA_URL = "https://www.reddit.com/captcha/{iden}"
FETCH_TIMEOUT = 10  # seconds
DEFAULT_COOLDOWN = 7200  # 2 hours on failure (seconds)


def _preprocess_image(img_bytes: bytes):
    """Pre-process CAPTCHA image for better OCR accuracy.

    Returns a PIL Image object, or None if PIL is not available.
    Steps: grayscale -> contrast boost -> sharpen -> resize 2x
    """
    try:
        from PIL import Image, ImageEnhance, ImageFilter

        img = Image.open(io.BytesIO(img_bytes)).convert("L")  # grayscale
        # Boost contrast
        img = ImageEnhance.Contrast(img).enhance(2.5)
        # Sharpen
        img = img.filter(ImageFilter.SHARPEN)
        # Resize 2x for better OCR
        w, h = img.size
        img = img.resize((w * 2, h * 2), Image.LANCZOS)
        return img
    except Exception as e:
        logger.debug("Image pre-processing failed: %s", e)
        return None


def _solve_with_ddddocr(img_bytes: bytes) -> Optional[str]:
    """Solve CAPTCHA using ddddocr (best open-source CAPTCHA OCR)."""
    try:
        import ddddocr

        ocr = ddddocr.DdddOcr(show_ad=False)
        result = ocr.classification(img_bytes)
        result = result.strip().replace(" ", "")
        logger.info("ddddocr solved CAPTCHA: '%s'", result)
        return result if result else None
    except ImportError:
        logger.debug("ddddocr not installed (pip install ddddocr)")
        return None
    except Exception as e:
        logger.debug("ddddocr failed: %s", e)
        return None


def _solve_with_tesseract(img_bytes: bytes) -> Optional[str]:
    """Solve CAPTCHA using Tesseract OCR with image pre-processing."""
    try:
        import pytesseract

        img = _preprocess_image(img_bytes)
        if img is None:
            # Fallback: open raw bytes if pre-processing failed
            try:
                from PIL import Image

                img = Image.open(io.BytesIO(img_bytes))
            except Exception:
                return None

        # Tesseract config: single-word mode, alphanumeric whitelist
        config = (
            "--psm 8 -c tessedit_char_whitelist="
            "abcdefghijklmnopqrstuvwxyz"
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "0123456789"
        )
        result = pytesseract.image_to_string(img, config=config)
        result = result.strip().replace(" ", "").replace("\n", "")
        logger.info("Tesseract solved CAPTCHA: '%s'", result)
        return result if len(result) >= 3 else None
    except ImportError:
        logger.debug(
            "pytesseract not installed "
            "(apt install tesseract-ocr && pip install pytesseract)"
        )
        return None
    except Exception as e:
        logger.debug("Tesseract failed: %s", e)
        return None


class RedditCaptchaSolver:
    """Fetches and solves Reddit CAPTCHA images with OCR fallback chain.

    Usage::

        solver = RedditCaptchaSolver(session)
        solution = solver.solve(iden)
        if solution:
            # retry POST with captcha_iden=iden, captcha_sol=solution
        elif solver.is_cooling_down:
            # wait before retrying

    Solver priority: ddddocr > Tesseract > give up (+ cooldown).
    """

    def __init__(
        self,
        session: requests.Session,
        cooldown_seconds: int = DEFAULT_COOLDOWN,
    ):
        self.session = session
        self.cooldown_seconds = cooldown_seconds

        # Stats
        self._attempts: int = 0
        self._solved: int = 0
        self._failed: int = 0

        # Cooldown state
        self._cooldown_until: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_image(self, iden: str) -> Optional[bytes]:
        """Download CAPTCHA image bytes from Reddit."""
        url = CAPTCHA_URL.format(iden=iden)
        try:
            resp = self.session.get(url, timeout=FETCH_TIMEOUT)
            if resp.status_code == 200 and resp.content:
                logger.debug(
                    "Fetched CAPTCHA image: %d bytes", len(resp.content)
                )
                return resp.content
            logger.warning("CAPTCHA fetch failed: HTTP %d", resp.status_code)
        except Exception as e:
            logger.warning("CAPTCHA fetch error: %s", e)
        return None

    def solve(self, iden: str) -> Optional[str]:
        """Fetch and solve a Reddit CAPTCHA.

        Returns solved text string, or None if unsolvable.
        Applies cooldown on failure so callers can check ``is_cooling_down``.
        """
        if self.is_cooling_down:
            remaining = self._cooldown_until - time.monotonic()
            logger.warning(
                "CAPTCHA solver in cooldown for %.0f more seconds", remaining
            )
            return None

        self._attempts += 1
        img_bytes = self.fetch_image(iden)
        if not img_bytes:
            self._failed += 1
            self._apply_cooldown()
            return None

        # Priority 1: ddddocr (best accuracy for distorted text)
        solution = _solve_with_ddddocr(img_bytes)
        if solution:
            self._solved += 1
            return solution

        # Priority 2: Tesseract
        solution = _solve_with_tesseract(img_bytes)
        if solution:
            self._solved += 1
            return solution

        # No solver could handle it
        logger.warning(
            "CAPTCHA unsolvable for iden=%s... (no solver available)",
            iden[:8],
        )
        self._failed += 1
        self._apply_cooldown()
        return None

    def solve_from_bytes(self, img_bytes: bytes) -> Optional[str]:
        """Solve a CAPTCHA from raw image bytes (no fetch needed).

        Useful when the caller already has the image data.
        """
        if self.is_cooling_down:
            remaining = self._cooldown_until - time.monotonic()
            logger.warning(
                "CAPTCHA solver in cooldown for %.0f more seconds", remaining
            )
            return None

        self._attempts += 1

        solution = _solve_with_ddddocr(img_bytes)
        if solution:
            self._solved += 1
            return solution

        solution = _solve_with_tesseract(img_bytes)
        if solution:
            self._solved += 1
            return solution

        self._failed += 1
        self._apply_cooldown()
        return None

    # ------------------------------------------------------------------
    # Cooldown
    # ------------------------------------------------------------------

    @property
    def is_cooling_down(self) -> bool:
        """True if the solver is in a failure cooldown period."""
        return time.monotonic() < self._cooldown_until

    @property
    def cooldown_remaining(self) -> float:
        """Seconds remaining in cooldown (0.0 if not cooling down)."""
        return max(0.0, self._cooldown_until - time.monotonic())

    def clear_cooldown(self) -> None:
        """Manually clear the cooldown (e.g. after a successful action)."""
        self._cooldown_until = 0.0

    def _apply_cooldown(self) -> None:
        """Set cooldown after a solver failure."""
        self._cooldown_until = time.monotonic() + self.cooldown_seconds
        logger.info(
            "CAPTCHA cooldown applied: %d seconds", self.cooldown_seconds
        )

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    @property
    def solve_rate(self) -> float:
        """Return fraction of CAPTCHAs solved (0.0-1.0)."""
        if not self._attempts:
            return 0.0
        return self._solved / self._attempts

    def stats(self) -> dict:
        """Return solver statistics."""
        return {
            "attempts": self._attempts,
            "solved": self._solved,
            "failed": self._failed,
            "solve_rate": round(self.solve_rate, 2),
            "cooling_down": self.is_cooling_down,
            "cooldown_remaining_s": round(self.cooldown_remaining, 1),
        }

    def reset_stats(self) -> None:
        """Reset all counters."""
        self._attempts = 0
        self._solved = 0
        self._failed = 0
