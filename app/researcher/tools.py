"""Tool schemas for supervisor and researcher agents (OpenAI function-calling format)."""

# ── Supervisor tools ──────────────────────────────────────────────────────────

THINK_TOOL = {
    "type": "function",
    "function": {
        "name": "think",
        "description": (
            "Use this to reflect on what you know so far, identify gaps, "
            "and plan your next research steps before acting."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "thought": {
                    "type": "string",
                    "description": "Your strategic reflection.",
                }
            },
            "required": ["thought"],
        },
    },
}

CONDUCT_RESEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "ConductResearch",
        "description": (
            "Delegate research to sub-researchers. Each topic spawns an "
            "independent researcher that searches the web, scrapes pages, "
            "and returns compressed findings. Provide detailed, specific topics."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "topics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "List of research topics to investigate in parallel. "
                        "Each should be a detailed description (at least a sentence)."
                    ),
                }
            },
            "required": ["topics"],
        },
    },
}

RESEARCH_COMPLETE_TOOL = {
    "type": "function",
    "function": {
        "name": "ResearchComplete",
        "description": (
            "Signal that research is complete and you have gathered sufficient "
            "evidence to write a comprehensive report."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Brief summary of what was accomplished.",
                }
            },
            "required": ["summary"],
        },
    },
}

SUPERVISOR_TOOLS = [THINK_TOOL, CONDUCT_RESEARCH_TOOL, RESEARCH_COMPLETE_TOOL]

# ── Researcher tools ──────────────────────────────────────────────────────────

SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the web for information. Returns a list of results with "
            "titles, URLs, and snippets."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query.",
                }
            },
            "required": ["query"],
        },
    },
}

SCRAPE_TOOL = {
    "type": "function",
    "function": {
        "name": "scrape_url",
        "description": (
            "Fetch and extract the text content of a webpage. "
            "Use this after web_search to read full articles."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to scrape.",
                }
            },
            "required": ["url"],
        },
    },
}

RESEARCHER_TOOLS = [SEARCH_TOOL, SCRAPE_TOOL]
