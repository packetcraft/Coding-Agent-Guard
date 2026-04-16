import json
import re
import base64

def truncate_output(text: str, max_chars: int = 4000) -> str:
    """Slice large payloads: extract first 2000 and last 2000 characters.
    Attackers often hide injections at boundaries to exploit LLM attention.
    """
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + "\n\n...[TRUNCATED]...\n\n" + text[-half:]


def try_decode_base64(text: str) -> tuple[str, list[str]]:
    """Detect and decode Base64 blobs within text for better classification.
    Returns:
        (text_with_decoded_segments, list_of_decoded_strings)
    """
    # Simple regex for potential base64 blobs (length >= 16)
    pattern = re.compile(r"(?:[A-Za-z0-9+/]{4}){4,}(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?")
    matches = pattern.findall(text)
    decoded_segments = []
    for m in matches:
        try:
            # Only add if it decodes to printable ASCII and is not trivial
            b = base64.b64decode(m)
            decoded = b.decode("ascii", errors="strict")
            if len(decoded) > 8 and any(c.isprintable() for c in decoded):
                decoded_segments.append(decoded)
        except Exception:
            continue
    if decoded_segments:
        hints = [f"[DECODED B64: {d}]" for d in decoded_segments]
        return text + "\n\n" + "\n".join(hints), decoded_segments
    return text, []


def extract_inspectable(tool_name: str, tool_input: dict) -> tuple[str, list[str]]:
    """Return the most security-relevant text and any decoded segments.

    Returns:
        (inspectable_text, decoded_segments)
    """
    raw_text = ""
    # Gemini CLI tool names are often lowercase (bash, write_file, edit_file, web_fetch)
    # Claude Code tool names are TitleCase (Bash, Write, Edit, WebFetch)
    tn_lower = tool_name.lower()

    if tn_lower in ["bash", "sh"]:
        raw_text = tool_input.get("command", "")
    elif "fetch" in tn_lower or "get" in tn_lower:
        raw_text = tool_input.get("url", "")
    elif "write" in tn_lower:
        path    = tool_input.get("file_path", "")
        content = tool_input.get("content", "")
        raw_text = f"file: {path}\n{truncate_output(content)}"
    elif "edit" in tn_lower or "patch" in tn_lower:
        path       = tool_input.get("file_path", "")
        new_string = tool_input.get("new_string", "")
        raw_text = f"file: {path}\n{truncate_output(new_string)}"
    else:
        # MCP tools and any unknown tools — dump full input (truncated)
        raw_text = truncate_output(json.dumps(tool_input, indent=2))

    return try_decode_base64(raw_text)
