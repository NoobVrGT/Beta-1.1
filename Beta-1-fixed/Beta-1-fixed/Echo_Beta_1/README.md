# Echo Beta 1 — repaired build

Echo is a small Python/Tkinter desktop study assistant. It includes local notes,
conversation history, an arithmetic calculator, a study checklist helper, and a
basic offline text outline command. Connected AI chat is optional.

## Requirements

- Python 3.10 or later
- Tkinter (included with most standard Windows and macOS Python installers; on
  some Linux distributions it is a separate system package)
- An internet connection and provider API key only for connected chat

There are no pip packages to install.

## Run on Windows

Open PowerShell in the `Echo_Beta_1` folder and run:

```powershell
py --version
py echo_beta1.py
```

If `py` is not available but `python` is, run `python echo_beta1.py` instead.

## Run on macOS/Linux

```bash
python3 --version
python3 echo_beta1.py
```

## Optional connected chat

Set environment variables in the same terminal before starting Echo. Do not put
API keys in the source code or commit them to GitHub.

### OpenAI-compatible API (OpenAI example)

PowerShell:

```powershell
$env:ECHO_API_KEY = "your_api_key_here"
$env:ECHO_API_URL = "https://api.openai.com/v1/chat/completions"
$env:ECHO_MODEL = "gpt-4o-mini"
py echo_beta1.py
```

### Groq example

Groq documents its OpenAI-compatible chat-completions endpoint as
`https://api.groq.com/openai/v1/chat/completions`. Use a model currently enabled
for your Groq account; check the provider's model list if a model is rejected.

PowerShell:

```powershell
$env:ECHO_API_KEY = "your_groq_api_key_here"
$env:ECHO_API_URL = "https://api.groq.com/openai/v1/chat/completions"
$env:ECHO_MODEL = "llama-3.3-70b-versatile"
py echo_beta1.py
```

These variables apply only to that terminal session. If you open a new terminal,
set them again. API usage may be subject to the provider's pricing and limits.

### About HTTP 403 / Cloudflare Error 1010

Echo now sends a descriptive `User-Agent` and gives more specific error messages.
Cloudflare documents Error 1010 as a request blocked based on the client's
request/browser signature. An error page containing that code is evidence of a
security-gateway block, but it does not alone identify why the request was
blocked or prove that the API key is wrong. Verify the exact official API URL,
model, key/provider match, and whether a proxy or network filter is in the path.
If Error 1010 persists against the documented endpoint, ask the provider or
network administrator for help; a client-side code change cannot guarantee a
provider-side block can be resolved.

## Offline commands

- `/help`
- `/calc 12 * (4 + 3)`
- `/study Geometry: parallel lines`
- `/summarize Paste text here`

Without an API key, these commands still work. Open-ended questions use a clear
offline fallback instead of pretending to be an AI model.

## Local data

Echo stores history and notes under `~/.echo_beta1/` in `history.json` and
`notes.json`. Data remains on the current computer. Avoid storing sensitive
information in this prototype.
