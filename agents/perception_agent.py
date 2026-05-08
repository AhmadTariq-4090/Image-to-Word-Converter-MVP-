import cv2
import numpy as np
from PIL import Image


class PerceptionAgent:
    """
    Perceives image properties and content to inform the Decision Agent.
    Analyzes: resolution, sharpness, brightness, contrast, content type.
    """

    MIN_RESOLUTION_PX = 100_000   # below this → low_resolution issue
    MIN_BLUR_SCORE    = 50        # Laplacian variance below this → blurry
    DARK_THRESHOLD    = 50        # mean brightness below this → too_dark
    BRIGHT_THRESHOLD  = 220       # mean brightness above this → too_bright
    LOW_CONTRAST      = 20        # std-dev below this → low_contrast

    # ── Public API ────────────────────────────────────────────────────────────

    def analyze(self, image: Image.Image) -> dict:
        """Run full perception analysis. Returns a structured report dict."""
        img_rgb  = np.array(image.convert("RGB"))
        gray     = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)

        width, height   = image.size
        resolution_px   = width * height
        blur_score      = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        brightness      = float(np.mean(gray))
        contrast        = float(np.std(gray))

        quality_score   = self._quality_score(resolution_px, blur_score, brightness, contrast)
        content_type    = self._content_type(gray, blur_score)
        issues          = self._issues(resolution_px, blur_score, brightness, contrast)
        preprocessing   = self._preprocessing_steps(issues)

        return {
            "width":                  width,
            "height":                 height,
            "resolution_px":          resolution_px,
            "blur_score":             round(blur_score, 2),
            "brightness":             round(brightness, 2),
            "contrast":               round(contrast, 2),
            "quality_score":          quality_score,        # 0–100
            "content_type":           content_type,         # printed | handwritten | mixed | low_quality
            "issues":                 issues,               # list of issue tags
            "suggested_preprocessing": preprocessing,       # list of step names
            "recommendation":         self._recommend(quality_score, content_type),
        }

    def preprocess(self, image: Image.Image, steps: list) -> Image.Image:
        """Apply preprocessing steps to improve OCR accuracy."""
        img_array = np.array(image.convert("RGB"))
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)

        if "denoise" in steps:
            gray = cv2.fastNlMeansDenoising(gray, h=10)

        if "threshold" in steps:
            _, gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        if "sharpen" in steps:
            kernel = np.array([[-1, -1, -1],
                                [-1,  9, -1],
                                [-1, -1, -1]])
            gray = cv2.filter2D(gray, -1, kernel)

        if "deskew" in steps:
            gray = self._deskew(gray)

        return Image.fromarray(gray)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _quality_score(self, resolution_px, blur_score, brightness, contrast) -> int:
        score = 100
        # Resolution penalty
        if resolution_px < self.MIN_RESOLUTION_PX:
            score -= 30
        elif resolution_px < 500_000:
            score -= 10
        # Blur penalty
        if blur_score < 20:
            score -= 40
        elif blur_score < self.MIN_BLUR_SCORE:
            score -= 20
        # Brightness penalty
        if brightness < self.DARK_THRESHOLD or brightness > self.BRIGHT_THRESHOLD:
            score -= 15
        # Contrast penalty
        if contrast < self.LOW_CONTRAST:
            score -= 15
        return max(0, min(100, score))

    def _content_type(self, gray: np.ndarray, blur_score: float) -> str:
        if blur_score < 20:
            return "low_quality"
        edges = cv2.Canny(gray, 50, 150)
        density = float(np.sum(edges > 0)) / edges.size
        if density > 0.15:
            return "handwritten"
        elif density > 0.05:
            return "mixed"
        return "printed"

    def _issues(self, resolution_px, blur_score, brightness, contrast) -> list:
        issues = []
        if resolution_px < self.MIN_RESOLUTION_PX:
            issues.append("low_resolution")
        if blur_score < self.MIN_BLUR_SCORE:
            issues.append("blurry")
        if brightness < self.DARK_THRESHOLD:
            issues.append("too_dark")
        elif brightness > self.BRIGHT_THRESHOLD:
            issues.append("too_bright")
        if contrast < self.LOW_CONTRAST:
            issues.append("low_contrast")
        return issues

    def _preprocessing_steps(self, issues: list) -> list:
        steps = []
        if "blurry" in issues:
            steps.append("sharpen")
        if "low_contrast" in issues or "too_dark" in issues:
            steps.append("threshold")
        if "blurry" in issues or "low_resolution" in issues:
            steps.append("denoise")
        return steps

    def _recommend(self, quality_score: int, content_type: str) -> str:
        if content_type in ("handwritten", "low_quality", "mixed"):
            return "gemini"
        if quality_score < 50:
            return "gemini"
        return "tesseract"

    def _deskew(self, gray: np.ndarray) -> np.ndarray:
        inverted = cv2.bitwise_not(gray)
        coords = np.column_stack(np.where(inverted > 0)).astype(np.float32)
        if len(coords) < 5:
            return gray
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        if abs(angle) < 0.5:
            return gray
        h, w = gray.shape
        M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
        return cv2.warpAffine(gray, M, (w, h),
                              flags=cv2.INTER_CUBIC,
                              borderMode=cv2.BORDER_REPLICATE)
