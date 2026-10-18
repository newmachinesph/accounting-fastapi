# AI Chat Accounting

![License: MIT](https://img.shields.io/badge/license-MIT-green) ![Python](https://img.shields.io/badge/python-3.10%2B-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-009688) ![Supabase](https://img.shields.io/badge/Supabase-3ECF8E)

A FastAPI backend for managing accounting data (companies, categories, payees, transactions) through a chat interface. An OpenAI-powered assistant calls accounting tools exposed by a FastMCP server, which in turn talks to the REST API. Data is stored in Supabase.

## Setup

```bash
pip install -r requirements.txt
pip install -r mcp_server/requirements.txt   # MCP server extras (also needs fastmcp)
```

Create a `.env` file:

```
OPENAI_API_KEY=your_openai_api_key
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
```

## Run

```bash
python main.py --port=8000     # API + chat UI; interactive docs at /docs
python mcp_server/server.py    # MCP server (set API_BASE_URL, default http://localhost:8000)
```

`mcp_config.json` shows how to register the MCP server in an MCP-capable client. `scripts/create_company.py` seeds a company with default categories (requires `SUPABASE_URL` and `SUPABASE_KEY` in the environment).

## Structure

- `main.py` - FastAPI app, chat streaming endpoint, middleware wiring
- `chat.html` - browser chat UI
- `api/` - routers and models for companies, categories, payees, transactions; health, error handling, rate limiting; agent clients
- `mcp_server/` - FastMCP server exposing the API as tools
- `temp_downloads.py` - short-lived download links for exports

## License

[MIT](LICENSE)
