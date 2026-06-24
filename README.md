# MinerBytsFree Server Build

Bu repo, `botfree.txt` userscriptini server lisansli hale getirmek icin hazirlandi.

## Klasorler

- `botfree.txt` - mevcut bot kaynak dosyasi
- `server/` - Render uzerinde calisacak FastAPI lisans ve bot dagitim serveri
- `panel/` - yerel Tkinter paneli
- `panel/generated_scripts/` - panelin uretecegi Tampermonkey scriptleri

## Lokal Server

```powershell
cd server
python -m pip install -r requirements.txt
copy .env.example .env
python -m uvicorn server:app --host 0.0.0.0 --port 10000
```

## Panel

```powershell
cd panel
python d.py
```

Panelden:

1. Server URL ve Admin Token gir.
2. `botfree.txt` sec.
3. `Botu Servera Yukle` bas.
4. `Key + Script Uret` ile kullaniciya ozel Tampermonkey scripti al.

## Supabase

SQL editor:

```sql
create table if not exists app_state (
  key text primary key,
  value jsonb not null,
  updated_at timestamptz default now()
);
```

Render env:

```text
ADMIN_TOKEN=...
SUPABASE_URL=...
SUPABASE_SERVICE_KEY=...
```

## Render

`render.yaml` temel ayari eklendi. GitHub'a push ettikten sonra Render'da blueprint olarak ya da manuel Web Service olarak kurulabilir.

