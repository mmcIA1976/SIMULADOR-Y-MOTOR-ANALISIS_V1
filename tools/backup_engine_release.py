"""Read-only, consistent public-schema backup before an engine rollout.

Credentials stay in the child environment. Dumps contain private app records and
must remain in ignored data/backups, outside Git. No restore is run against DB.
"""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from psycopg.conninfo import conninfo_to_dict

ROOT = Path(__file__).resolve().parents[1]


def main():
    env = os.environ.copy()
    for filename in ('.env.local', '.env'):
        path = ROOT / filename
        if path.exists():
            for line in path.read_text(encoding='utf-8').splitlines():
                if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    connection = env.get('SUPABASE_DATABASE_URL') or env.get('DATABASE_URL')
    if not connection or not connection.startswith(('postgres://', 'postgresql://')):
        raise RuntimeError('Postgres connection is required')
    parameters = conninfo_to_dict(connection)
    for key, value in parameters.items():
        env['PG' + key.upper()] = value
    env['PGDATABASE'] = parameters.get('dbname', 'postgres')
    env['PGCONNECT_TIMEOUT'] = '15'
    # pg_dump needs session semantics; use the same Supabase pooler's session
    # port instead of the application's transaction pool (same DB and role).
    if parameters.get('host', '').endswith('.pooler.supabase.com') and parameters.get('port') == '6543':
        env['PGPORT'] = '5432'
    binaries = Path(r'C:\Program Files\PostgreSQL\17\bin')
    if '--probe-native' in sys.argv:
        result = subprocess.run([str(binaries/'psql.exe'), '--no-password',
            '--command', 'select 1'],env=env,capture_output=True,text=True,timeout=30)
        print(json.dumps(dict(returncode=result.returncode,stdout=result.stdout,
            stderr=result.stderr.replace(connection,'[REDACTED]'))))
        return
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    directory = ROOT / 'data' / 'backups' / ('engine_release_' + stamp)
    directory.mkdir(parents=True)
    dump = directory / 'public.dump'
    started = datetime.now(timezone.utc).isoformat()
    log = directory / 'pg_dump.log'
    print(json.dumps(dict(backup_started=str(directory))), flush=True)
    with log.open('w',encoding='utf-8') as errors:
        result = subprocess.run([str(binaries / 'pg_dump.exe'), '--format=custom', '--verbose',
            '--no-owner', '--no-acl', '--no-password', '--schema=public', '--lock-wait-timeout=15000',
            '--file', str(dump)], env=env, stdout=subprocess.DEVNULL, stderr=errors, timeout=3600)
    if result.returncode:
        # Do not echo the connection URL, even if a vendor error contains it.
        error = log.read_text(encoding='utf-8').replace(connection, '[REDACTED]')
        raise RuntimeError('pg_dump failed: ' + error[-1800:])
    listing = subprocess.run([str(binaries / 'pg_restore.exe'), '--list', str(dump)],
        check=True, capture_output=True, text=True).stdout
    (directory / 'restore_inventory.txt').write_text(listing, encoding='utf-8')
    subprocess.run([str(binaries / 'pg_restore.exe'), '--file', os.devnull, str(dump)],
        check=True, capture_output=True)
    tables = sorted(line.split(' TABLE DATA public ', 1)[1].rsplit(' ', 1)[0]
        for line in listing.splitlines() if ' TABLE DATA public ' in line)
    if not {'recommendations', 'operations', 'learning_evaluations', 'contest_seasons',
            'operation_observation_checkpoints'}.issubset(tables):
        raise RuntimeError('backup is missing critical app tables')
    digest = sha256()
    with dump.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    manifest = dict(started_at=started, completed_at=datetime.now(timezone.utc).isoformat(),
        schema='public', format='postgresql-custom', server_changes=0,
        archive_sha256=digest.hexdigest(), bytes=dump.stat().st_size,
        tables=tables, archive_stream_read_verified=True,
        restore_executed=False, excludes='Supabase managed schemas and storage objects')
    (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(backup=str(directory), **manifest)))


if __name__ == '__main__':
    main()
