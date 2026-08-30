# NRZ Student Management - Windows Deployment Fix Documentation

## Problem Summary

The Windows installer was failing with "setup files are corrupted" error, and the application was not installing properly to `Program Files`. Multiple issues were present:

### Issues Identified

1. **APScheduler starting during PyInstaller analysis** - The Django app's `ready()` method in `school/apps.py` was starting the scheduler during PyInstaller's module analysis phase, causing build failures.

2. **Missing database tables** - The installed application wasn't running migrations on first launch, causing `django.db.utils.OperationalError: no such table: django_session` errors.

3. **Static files not found** - The `STATICFILES_DIRS` setting pointed to a path that didn't exist in the packaged executable.

4. **Installer not copying files to Program Files** - The Inno Setup script had a `Check` function that was failing silently, preventing file installation.

5. **Database corruption in installer** - The `[Files]` section was trying to copy `data/` and `backups/` directories which contained SQLite files that were locked or caused corruption.

6. **No automatic migrations** - The application required manual migration runs after installation.

---

## Solutions Implemented

### 1. Fixed APScheduler During Build

**File:** `school/apps.py`

Added environment variable check to disable scheduler during PyInstaller analysis:

```python
def ready(self):
    # Skip scheduler during PyInstaller analysis or when explicitly disabled
    if getattr(sys, 'frozen', False) or os.environ.get('NRZ_DISABLE_SCHEDULER') == '1':
        return
    # ... rest of ready() method
```

**Build command:**
```powershell
$env:NRZ_DISABLE_SCHEDULER="1"; pyinstaller nrz_student_management.spec --noconfirm
```

### 2. Automatic Migrations on Startup

**File:** `launcher.py`

Added `run_migrations()` function that runs before starting Django:

```python
def run_migrations():
    """Run Django migrations to ensure database tables exist."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    execute_from_command_line([
        "manage.py",
        "migrate",
        "--noinput",
    ])

def main():
    # Run migrations first (idempotent, safe to run every time)
    print("Running database migrations...")
    run_migrations()
    print("Migrations complete.")
    # ... start Django server
```

This ensures all Django tables (`django_session`, `auth_*`, `school_*`, etc.) are created automatically on first run.

### 3. Portable Path Configuration

**File:** `config/paths.py`

Created portable path detection that works in both development and packaged environments:

```python
def application_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent

APP_DIR = application_dir()
DATA_DIR = APP_DIR / "data"
STATIC_DIR = APP_DIR / "static"
TEMPLATES_DIR = APP_DIR / "templates"
```

**File:** `config/settings.py`

Updated to use `APP_DATA_DIR` from environment variable:

```python
APP_DATA_DIR = Path(
    os.environ.get("NRZ_DATA_DIR", DATA_DIR)
)
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": APP_DATA_DIR / "school.sqlite3",
    }
}
```

### 4. Fixed Inno Setup Installer

**File:** `NRZ_Student_Management.iss`

**Key fixes:**

1. **Removed corrupted data files from [Files] section:**
   ```iss
   ; Note: data/ and backups/ are NOT included - they will be created fresh in ProgramData
   ; The SQLite database will be created automatically by Django on first run
   ```

2. **Removed problematic Check function** that was silently failing.

3. **Added proper error handling and logging:**
   ```iss
   function InitializeSetup(): Boolean;
   begin
     Result := True;
     // Verify source directory exists
     if not DirExists(ExpandConstant('{#SourceDir}')) then
       MsgBox('ERROR: Source directory not found...', mbCriticalError, MB_OK);
       Result := False;
   end;
   ```

4. **Added post-install directory creation with permissions:**
   ```iss
   procedure CurStepChanged(CurStep: TSetupStep);
   begin
     if CurStep = ssPostInstall then
     begin
       ForceDirectories(ExpandConstant('{#DataDir}'));
       ForceDirectories(ExpandConstant('{#DataDir}') + '\backups');
       Exec('icacls.exe', '{#DataDir} /grant "Users:(OI)(CI)F" /T', '', SW_HIDE, ewWaitUntilTerminated, ErrCode);
     end;
   end;
   ```

5. **Registry entry for NRZ_DATA_DIR:**
   ```iss
   [Registry]
   Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; 
   ValueType: expandsz; ValueName: "NRZ_DATA_DIR"; ValueData: "{#DataDir}"; Flags: preservestringtype
   ```

### 5. Data Directory Separation

**Architecture:**
```
Program Files\NRZ Student Management\     (read-only application files)
    ├── NRZ Student Management.exe
    ├── _internal\                        (Python, Django, dependencies)
    └── unins000.exe                      (uninstaller)

ProgramData\NRZ Student Management\       (writable data)
    ├── school.sqlite3                    (SQLite database)
    └── backups\                          (backup files)
```

This separation allows:
- Application updates without affecting user data
- Multiple users on same machine sharing data
- Proper Windows security model (Program Files = read-only, ProgramData = writable)

---

## Build & Deploy Commands

### Development
```powershell
# Run normally
.\.venv\Scripts\Activate.ps1
python launcher.py

# Or with Django directly
python manage.py runserver
```

### Build Executable
```powershell
.\.venv\Scripts\Activate.ps1
$env:NRZ_DISABLE_SCHEDULER="1"
pyinstaller nrz_student_management.spec --noconfirm
```

### Build Installer
```powershell
"C:\Program Files\Inno Setup 7\ISCC.exe" NRZ_Student_Management.iss
```

Output: `installer/NRZ_Student_Management_Setup_1.0.0.exe`

### Test Installation
```powershell
# Silent install
installer\NRZ_Student_Management_Setup_1.0.0.exe /SILENT

# Verify
ls "C:\Program Files\NRZ Student Management"
ls "C:\ProgramData\NRZ Student Management"
reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v NRZ_DATA_DIR
```

---

## Verification Checklist

After installation, verify:

- [ ] `C:\Program Files\NRZ Student Management\NRZ Student Management.exe` exists
- [ ] `C:\Program Files\NRZ Student Management\_internal\` contains Python/Django
- [ ] `C:\ProgramData\NRZ Student Management\school.sqlite3` exists (created on first run)
- [ ] `C:\ProgramData\NRZ Student Management\backups\` directory exists
- [ ] `NRZ_DATA_DIR` environment variable set to `C:\ProgramData\NRZ Student Management`
- [ ] Desktop/Start Menu shortcuts created
- [ ] Application launches and runs migrations automatically
- [ ] Browser opens to `http://127.0.0.1:8000`
- [ ] Login works, dashboard loads, all features functional

---

## Files Modified/Created

| File | Purpose |
|------|---------|
| `school/apps.py` | Disabled scheduler during PyInstaller build |
| `launcher.py` | Added automatic migration runner |
| `config/paths.py` | Portable path detection |
| `config/settings.py` | Environment-based data directory |
| `NRZ_Student_Management.iss` | Fixed Inno Setup installer with error handling |
| `nrz_student_management.spec` | PyInstaller spec with all dependencies |

---

## Key Lessons

1. **Separate application code from user data** - Use `Program Files` for app, `ProgramData` for database
2. **Run migrations automatically** - Don't require manual steps after install
3. **Disable background services during build** - Use environment variables to control app behavior
4. **Test installer silently** - Use `/SILENT` flag for automation
3. **Log everything** - Inno Setup `Log()` calls help debug installation issues
4. **Verify source exists** - Check `DirExists()` before copying in installer