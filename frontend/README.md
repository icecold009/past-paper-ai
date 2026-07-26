# Past Paper AI frontend

This Vite/React app is the functional frontend slice. It uses the FastAPI backend's subjects, questions, attempts,
mastery, and weak-spot paper endpoints. The dashboard highlights the lowest evidenced topic/command-word scores,
drills into the existing question screen with both filters applied, and can generate a paper that visibly labels real
past-paper questions separately from AI-generated fallback questions. Authentication is intentionally represented by
an in-memory development user ID.

## Local development

From the repository root, start the backend in one terminal:

```powershell
.venv\Scripts\python.exe -m uvicorn api.main:app --reload
```

Then start the frontend in a second terminal:

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

Open `http://127.0.0.1:5173`. The Vite development proxy forwards `/api/*` to the backend at
`http://127.0.0.1:8000/*`.
