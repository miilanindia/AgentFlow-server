# AgentFlow Backend

This is the FastAPI backend for the AI Browser Agent.

## Getting Started

1. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   playwright install
   ```

3. Set up your environment variables by copying `.env.example` to `.env` and filling in the values. Ensure you have a valid Neon PostgreSQL `DATABASE_URL`.

4. Run database migrations:
   ```bash
   alembic upgrade head
   ```

5. Start the server:
   ```bash
   uvicorn app.main:app --reload
   ```
