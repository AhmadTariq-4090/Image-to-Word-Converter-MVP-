class FeedbackAgent:
    """
    Records user corrections and satisfaction signals.
    Updates the MemoryStore so the Decision Agent learns over time.
    """

    def __init__(self, memory_store):
        self.memory = memory_store

    # ── Public API ────────────────────────────────────────────────────────────

    def record_satisfaction(self, session_id: str, engine_used: str,
                             content_type: str, satisfied: bool):
        """
        Called when the user gives a thumbs-up/down.
        Updates engine preference in long-term memory.
        """
        satisfaction = 0.9 if satisfied else 0.2
        self.memory.update_engine_preference(content_type, engine_used, satisfaction)

        sentiment = "satisfied" if satisfied else "unsatisfied"
        self.memory.log(session_id, "INFO",
                        f"User {sentiment} with {engine_used} on '{content_type}' content")

    def record_correction(self, session_id: str, image_hash: str,
                          original_text: str, corrected_text: str,
                          engine_used: str, content_type: str):
        """
        Called when the user submits a manual text correction.
        Saves the correction and infers that the current engine was sub-optimal.
        """
        self.memory.save_correction(session_id, image_hash, original_text, corrected_text)

        # If the user had to correct Tesseract output, prefer Gemini next time
        if engine_used == "tesseract":
            self.memory.update_engine_preference(content_type, "gemini", satisfaction=0.25)
        else:
            # Even Gemini needed correction; record low satisfaction
            self.memory.update_engine_preference(content_type, "gemini", satisfaction=0.4)

        self.memory.log(session_id, "INFO",
                        f"Correction submitted for hash={image_hash} "
                        f"(engine={engine_used}, content_type={content_type})")
