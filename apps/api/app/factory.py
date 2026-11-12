from adapters.llm.gateway import GroqProvider, OrganizerProvider, UnconfiguredGateway


def gateway(settings, corpus):
    if settings.llm_provider == "disabled":
        return UnconfiguredGateway()
    common = {"model": settings.llm_model, "corpus": corpus, "timeout": settings.llm_timeout}
    try:
        if settings.llm_provider == "groq":
            return GroqProvider(api_key=settings.groq_api_key.get_secret_value(), **common)
        return OrganizerProvider(
            base_url=settings.organizer_base_url,
            api_key=settings.organizer_api_key.get_secret_value(),
            **common,
        )
    except ValueError:
        raise RuntimeError("LLM configuration is incomplete; check .env.example") from None
