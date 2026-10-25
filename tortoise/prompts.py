"""Every prompt the hare and the tortoise see. Both get the same answer rules, so the
only difference between them is how slowly they work."""

ANSWER_RULES = (
    "Answer with the shortest exact phrase that answers the question: usually a name, "
    "a place, a date, a number or a few words. For yes/no questions answer exactly "
    "'yes' or 'no'. Never answer with a full sentence."
)

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {"reasoning": {"type": "string"}, "answer": {"type": "string"}},
    "required": ["reasoning", "answer"],
}

READ_SCHEMA = {
    "type": "object",
    "properties": {
        "relevant": {"type": "boolean"},
        "facts": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
    },
    "required": ["relevant", "facts"],
}

VERIFY_SCHEMA = {
    "type": "object",
    "properties": {"supported": {"type": "boolean"}, "short_answer": {"type": "string"}},
    "required": ["supported", "short_answer"],
}


def _para(p: dict) -> str:
    return f"[{p['title']}] {p['text']}"


def hare(question: str, paragraphs: list) -> str:
    docs = "\n\n".join(_para(p) for p in paragraphs)
    return (
        f"DOCUMENTS:\n{docs}\n\nQUESTION: {question}\n\n"
        "The answer needs facts from the documents, sometimes from two of them. "
        "Think in one or two sentences in 'reasoning', then give the answer.\n"
        f"{ANSWER_RULES}"
    )


def read(question: str, paragraph: dict, known: list) -> str:
    known_txt = ""
    if known:
        known_txt = (
            "\nWHAT IS ALREADY KNOWN (from other paragraphs):\n"
            + "\n".join(f"- {k['fact']} ({k['title']})" for k in known)
            + "\nUse this: a paragraph can matter because it is about something mentioned above.\n"
        )
    return (
        f"QUESTION: {question}\n{known_txt}\n"
        f"PARAGRAPH\n{_para(paragraph)}\n\n"
        "Does this paragraph contain a fact needed to answer the question, even if it is only "
        "one step of a two-step answer? If yes, set relevant=true and copy up to 3 short facts "
        "from it, each a self-contained sentence that names its subject. If no, set "
        "relevant=false and facts=[]."
    )


def _notes(known: list) -> str:
    if not known:
        return "(no relevant facts were found)"
    return "\n".join(f"- {k['fact']} ({k['title']})" for k in known)


def _sources(paras) -> str:
    if not paras:
        return ""
    return "SOURCE PARAGRAPHS (the ones you flagged as relevant):\n" + "\n\n".join(_para(p) for p in paras) + "\n\n"


def draft(question: str, known: list, paras=None) -> str:
    return (
        _sources(paras) +
        f"NOTES (facts collected by reading every document carefully):\n{_notes(known)}\n\n"
        f"QUESTION: {question}\n\n"
        "Connect the notes step by step in 'reasoning' (two sentences at most), then answer.\n"
        f"{ANSWER_RULES}"
    )


def verify(question: str, known: list, candidate: str, paras=None) -> str:
    return (
        _sources(paras) +
        f"NOTES:\n{_notes(known)}\n\nQUESTION: {question}\n"
        f"PROPOSED ANSWER: {candidate}\n\n"
        "Is the proposed answer directly supported by the notes and sources? Set supported=true only if "
        "the notes back it up. In short_answer, rewrite the proposed answer as the shortest "
        f"exact phrase. {ANSWER_RULES}"
    )
