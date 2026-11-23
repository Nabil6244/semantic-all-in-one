# Make videos from Claude (Semantic YT Studio MCP)

This lets Claude (the Claude desktop app or Claude Code) make videos with Semantic YT Studio from a chat:
write the CSV, start the render, follow it, and queue an overnight batch. It is free: no API key, no
hosting, nothing to buy. Claude chats count toward your normal Claude plan's usage, like any other chat.

Renders run on your own computer with the same engine as the app, at the same speed.

---

## What you need

1. **Semantic YT Studio** installed and **signed in once** (open it, sign in, close it).
2. **Python 3.10 or newer**.
   - Mac: usually already there. Check in Terminal: `python3 --version`
   - Windows: install from python.org and tick **"Add python.exe to PATH"**. Check in a terminal: `py --version`
3. **Two files** in one folder (any folder, e.g. `Documents\StudioMCP`):
   - `studio_mcp.py`
   - `make_video.py`

Nothing else is installed: both files use only Python's own library.

---

## Connect it to Claude Desktop (Chat)

1. In Claude Desktop open **Settings → Developer → Edit Config**. That opens `claude_desktop_config.json`:
   - Mac: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`
2. Put this in it (keep any servers already there inside `mcpServers`), with your own folder path:

**Mac**
```json
{
  "mcpServers": {
    "studio": {
      "command": "python3",
      "args": ["/Users/YOU/Documents/StudioMCP/studio_mcp.py"]
    }
  }
}
```

**Windows**: every `\` in a path is written twice.
```json
{
  "mcpServers": {
    "studio": {
      "command": "py",
      "args": ["C:\\Users\\YOU\\Documents\\StudioMCP\\studio_mcp.py"]
    }
  }
}
```

3. Quit Claude Desktop completely and open it again. The **studio** tools now show in the tools menu of a new chat.

## Connect it to Claude Code

In a terminal:

```bash
claude mcp add studio --scope user -- python3 /Users/YOU/Documents/StudioMCP/studio_mcp.py
```

Windows:

```bash
claude mcp add studio --scope user -- py C:\Users\YOU\Documents\StudioMCP\studio_mcp.py
```

`--scope user` makes it available in every folder. Check it with `claude mcp list`.

---

## Try it

Start a new chat and say, for example:

- "What video styles can studio make?"
- "Get the CSV rules for the war style, write the CSV for this script, save it next to it, then start the video with my voiceover `C:\Videos\vo.mp3`."
- "How is my video doing?"
- "Queue these three videos overnight: …"

Claude asks before each tool the first time; allow it.

## The tools

| Tool | What it does |
|---|---|
| `list_styles` | The styles that run without clicks, and whether each needs a CSV and a voiceover |
| `get_csv_prompt` | The CSV-writing rules for one style |
| `start_video` | Starts one video in the background; the app opens and presses its own buttons |
| `job_status` | Where a video is: step, finished video path, or why it failed, plus the last log lines |
| `list_jobs` | Recent videos and overnight batch reports |
| `stop_job` | Stops a video this server started |
| `queue_overnight` | Several videos one after another; one failure never stops the rest; a report is written |

Good to know:

- A render **keeps going if you close Claude**. Ask "how is my video doing?" in any later chat.
- It **will not start while the app is already open** (it shares the app's Flow accounts). Close the app, or tell Claude to run alongside it.
- Jobs, logs and reports are kept in `~/.videogen/jobs` (Windows: `C:\Users\YOU\.videogen\jobs`).

---

## If something goes wrong

| What you see | Fix |
|---|---|
| No studio tools in Claude | Fully quit and reopen Claude Desktop. Check the JSON has no missing comma and Windows paths use `\\`. |
| "spawn python3 ENOENT" / "py not found" | Use the full Python path as `command`, e.g. `/usr/local/bin/python3` or `C:\\Python312\\python.exe` (find it with `which python3` / `where py`). |
| "Semantic YT Studio was not found" | Install the app in the normal place (Applications on Mac, the default folder on Windows). |
| "is already open" | Close the app (or wait for a running batch), then ask again. |
| The job waits at the start | The app is asking you to sign in; sign in once in its window. |
| A video failed | Ask Claude "why did it fail?": it reads `job_status`, fixes the CSV and starts it again. |
