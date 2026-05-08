class DecisionAgent:
    """
    Selects the optimal OCR engine and preprocessing pipeline based on:
      - PerceptionAgent report
      - Long-term engine preferences stored in memory
      - API key availability (hard constraint)
    """

    # ── Public API ────────────────────────────────────────────────────────────

    def decide(self,
               perception: dict,
               memory_prefs: dict = None,
               api_key_available: bool = True) -> dict:
        """
        Returns a decision dict:
          engine            – 'tesseract' or 'gemini'
          preprocessing     – list of preprocessing step names
          fallback_used     – True if Gemini was preferred but unavailable
          confidence_expected – float 0–1
          rationale         – human-readable explanation
        """
        engine = perception["recommendation"]   # start from perception's suggestion

        # Override with memory-learned preference if confidence is high enough
        if memory_prefs:
            ct = perception["content_type"]
            pref = memory_prefs.get(ct)
            if pref and pref.get("confidence", 0) >= 0.65 and pref.get("usage_count", 0) >= 3:
                engine = pref["preferred_engine"]

        # Hard constraint: Gemini requires API key
        fallback = False
        if engine == "gemini" and not api_key_available:
            engine = "tesseract"
            fallback = True

        return {
            "engine":               engine,
            "preprocessing":        perception["suggested_preprocessing"],
            "fallback_used":        fallback,
            "confidence_expected":  self._estimate_confidence(engine, perception["quality_score"]),
            "rationale":            self._rationale(engine, perception, fallback, memory_prefs),
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    def _estimate_confidence(self, engine: str, quality_score: int) -> float:
        base = 0.90 if engine == "gemini" else 0.75
        # Adjust ±0.25 based on quality score relative to 50
        adjustment = (quality_score - 50) / 200.0
        return round(min(1.0, max(0.2, base + adjustment)), 2)

    def _rationale(self, engine: str, perception: dict,
                   fallback: bool, memory_prefs: dict) -> str:
        reasons = []
        ct  = perception["content_type"]
        qs  = perception["quality_score"]
        iss = perception["issues"]

        if engine == "gemini":
            if ct == "handwritten":
                reasons.append("handwritten content detected")
            if ct == "low_quality" or qs < 50:
                reasons.append(f"low image quality (score {qs}/100)")
            if ct == "mixed":
                reasons.append("mixed layout detected")
            if memory_prefs and ct in memory_prefs:
                p = memory_prefs[ct]
                reasons.append(f"memory: preferred for '{ct}' "
                                f"({p.get('usage_count',0)} samples, "
                                f"{p.get('confidence',0)*100:.0f}% satisfaction)")
        else:
            reasons.append(f"clean printed text (quality {qs}/100)")

        if fallback:
            reasons.append("Gemini preferred but API key not provided → using Tesseract")
        if iss:
            reasons.append(f"auto-preprocessing for: {', '.join(iss)}")

        return "; ".join(reasons) if reasons else "standard processing"
