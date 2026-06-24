MINERBYTSFREE SERVER

Render icin temel FastAPI server.

Komut:
  pip install -r requirements.txt
  uvicorn server:app --host 0.0.0.0 --port 10000

Render start command:
  uvicorn server:app --host 0.0.0.0 --port $PORT

Gerekli env:
  ADMIN_TOKEN
  SUPABASE_URL
  SUPABASE_SERVICE_KEY

Supabase tablo:
  create table if not exists app_state (
    key text primary key,
    value jsonb not null,
    updated_at timestamptz default now()
  );

Admin endpointleri:
  GET  /health
  GET  /admin/licenses
  POST /admin/license/create
  POST /admin/license/toggle
  POST /admin/license/key
  POST /admin/license/delete
  POST /admin/bot/upload

Client endpointleri:
  POST /api/auth
  POST /api/heartbeat
  GET  /api/bot/bundle

